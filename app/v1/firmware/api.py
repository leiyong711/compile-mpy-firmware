# !/usr/bin/env python
# -*- coding:utf-8 -*-
# project name: compile-mpy-firmware
# author: "Lei Yong" 
# creation time: 2023-11-28 20:03
# Email: leiyong711@163.com

import io
import os
import shutil
import traceback
import threading
from utils.log import lg
from utils.config import Config
from utils.constants import APP_PATH
from utils.tools import generate_random_number, compress_folder, sign_md5
from utils.exception_handling import *
from typing import List
from .db_model import Firmware, FirmwareWaitCompiled, text
from .api_model import CreateCompilationTaskOUT, GetFirmwareListOut, GetFirmwareWaitCompiledListOut
from dbs.sqlite_connect import SessionLocal, Session
from fastapi import APIRouter, Request, File, UploadFile, Form, Depends, Query
from fastapi.responses import FileResponse, Response, JSONResponse, StreamingResponse
# from fastapi.responses import JSONRespons


app = APIRouter()
config = Config()


# 依赖函数，用于获取数据库会话
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.post("/test")
async def test(commond: str = File(..., title="命令"),):
    from utils.tools import excuting_command
    status, result = excuting_command(commond, timeout_seconds=300)
    lg.debug(f"status: {status}\tresult: {result}")
    return JSONResponse({"status": status, "result": result})


@app.post("/upload", tags=[], summary="创建编译任务", response_model=CreateCompilationTaskOUT, responses={422: {'model': ErrorOUt}})
async def upload_file(
        files: List[UploadFile] = File(..., title="待编译固件文件"),
        device_type: str = Form(..., title="设备类型"),
        flash_size: str = Form(..., title="Flash大小"),
        email: str = Form(..., title="邮箱"),
        password: str = Form('', title="提取密码"),
        remark: str = Form('', title="备注"),
        db: Session = Depends(get_db)
):
    filename_dir = generate_random_number()
    upload_dir = config.get_jsonpath("ProjectConfig.upload_dir", 'upload')
    temporary_folder = f"{APP_PATH}{upload_dir}/{filename_dir}"
    try:

        if not os.path.exists(temporary_folder):
            os.makedirs(temporary_folder)

        for file in files:
            # 获取文件的原始文件名
            filename = file.filename
            # 构建保存文件的路径
            save_path = os.path.join(temporary_folder, filename)

            # 保存文件
            with open(save_path, "wb") as f:
                contents = await file.read()
                f.write(contents)

        # 初步压缩文件夹，等待后续定时任务进行编译
        compress_folder(temporary_folder, temporary_folder)

        params = {
            "email": email,                 # 邮箱
            "device_type": device_type,  # 设备类型
            "flash_size": flash_size,       # Flash大小
            "status": 3,                    # 编译状态,0:编译成功,1:编译失败,2:编译中,3:等待编译
            "remark": remark,               # 备注
            "custom_source_code_file_path": f"{upload_dir}/{filename_dir}.zip",  # 自定义源码文件路径
        }

        # 提取密码
        if password:
            params['retrieve_password'] = await sign_md5(password)

        new_instance = FirmwareWaitCompiled(**params)
        db.add(new_instance)
        db.commit()
        db.refresh(new_instance)

        # 获取新记录的 ID
        new_instance_id = new_instance.id

        # lg.debug(f"收到文件：{files}\t设备: {device_type}\t大小: {flash_size}\t邮箱：{email}\t密码：{password}\t备注：{remark}")
        return {"data": {"id": new_instance_id, "msg": "创建编译任务成功"}}
    except:
        lg.error(f"创建编译任务异常：{traceback.format_exc()}")
        raise UnicornException(code=50000, message="上传异常，请重试")
    finally:
        # 删除临时文件夹
        if os.path.exists(temporary_folder):
            shutil.rmtree(temporary_folder)
        if hasattr(db, "close"):
            db.close()


@app.get("/get_firmware_wait_compiled_list", summary="查询待编译固件列表", tags=["固件管理"], response_model=GetFirmwareWaitCompiledListOut,
         responses={422: {'model': ErrorOUt}})
async def get_firmware_wait_compiled_list(*,
                            page: int = Query(..., title="当前页码", gt=0, example=1),
                            limit: int = Query(..., title="每页数量", gt=0, example=20),
                            id: str = Query(None, alias="id", title="待编译ID", example=None),
                            email: str = Query(None, title="邮箱",example=None),
                            flash_size: str = Query(None, title="闪存大小",example='all'),
                            device_type: str = Query(None, title="设备类型", example="all"),
                            sort: str = Query(..., title="排序方式", example="+id"),
                            db: Session = Depends(get_db)):

    flash_size_mapping = {"all": None, "2M": "2M", "4M": "4M", "8M": "8M", "16M": "16M"}
    device_type_mapping = {"all": None, "ESP8266": "ESP8266", "ESP32_S": "ESP32_S", "ESP32_S2": "ESP32_S2", "ESP32_S3": "ESP32_S3", "ESP32_C3": "ESP32_C3"}

    flash_size = flash_size_mapping.get(flash_size, None)
    device_type = device_type_mapping.get(device_type, None)

    try:
        if sort == "+id":
            firmware_wait_compiled = db.query(FirmwareWaitCompiled).filter(
                FirmwareWaitCompiled.id == id if id else text(""),
                FirmwareWaitCompiled.email.like("%" + email + "%") if email else text(""),
                FirmwareWaitCompiled.flash_size == flash_size if flash_size else text(""),
                FirmwareWaitCompiled.device_type == device_type if device_type else text("")
            )
        else:
            firmware_wait_compiled = db.query(FirmwareWaitCompiled).order_by(FirmwareWaitCompiled.id.desc()).filter(
                FirmwareWaitCompiled.id == id if id else text(""),
                FirmwareWaitCompiled.email.like("%" + email + "%") if email else text(""),
                FirmwareWaitCompiled.flash_size == flash_size if flash_size else text(""),
                FirmwareWaitCompiled.device_type == device_type if device_type else text("")
            )
        try:
            total = firmware_wait_compiled.count()
        except UnboundLocalError:
            total = 0

        try:
            items = firmware_wait_compiled.offset((page - 1) * limit).limit(limit).all()
        except UnboundLocalError:
            items = []

        return {"data": {"items": items, "total": total}}
    except:
        lg.error(f"查询待编译固件列表异常：{traceback.format_exc()}")
        raise UnicornException(message="系统内部错误")
    finally:
        if hasattr(db, "close"):
            db.close()

@app.get("/get_firmware_list", summary="查询已编译固件", tags=["固件管理"], response_model=GetFirmwareListOut,
         responses={422: {'model': ErrorOUt}})
async def get_firmware_list(*,
                        page: int = Query(..., title="当前页码", gt=0, example=1),
                        limit: int = Query(..., title="每页数量", gt=0, example=20),
                        id: str = Query(None, alias="id", title="固件ID", example=None),
                        email: str = Query(None, title="邮箱",example=None),
                        flash_size: str = Query(None, title="闪存大小",example='all'),
                        device_type: str = Query(None, title="设备类型", example="all"),
                        sort: str = Query(..., title="排序方式", example="+id"),
                        db: Session = Depends(get_db)):

    # params = {
    #     "device_type": "ESP32",
    #     "flash_size": "2M",
    #     "email": "leiyong@163.com",
    #     "firmware_file_path": "D:\Code2\compile-mpy-firmware\res_pack\esp8266-20190125-v1.10.bin",
    #     "custom_source_code_file_path": "D:\Code2\compile-mpy-firmware/res_pack/upload/20231206194741133507718130.zip",
    #     "remark": "测试",
    #     "upload_time": "2023-12-06 19:47:41.179478",
    #     "start_compilation_time": "2023-12-06 20:47:41.179478",
    #     "compilation_time_consuming": 600
    #
    # }
    # new_instance = Firmware(**params)
    # db.add(new_instance)
    # db.commit()
    # db.refresh(new_instance)

    flash_size_mapping = {"all": None, "2M": "2M", "4M": "4M", "8M": "8M", "16M": "16M"}
    device_type_mapping = {"all": None, "ESP8266": "ESP8266", "ESP32_S": "ESP32_S", "ESP32_S2": "ESP32_S2", "ESP32_S3": "ESP32_S3", "ESP32_C3": "ESP32_C3"}

    flash_size = flash_size_mapping.get(flash_size, None)
    device_type = device_type_mapping.get(device_type, None)

    try:
        if sort == "+id":
            firmware = db.query(Firmware).filter(
                Firmware.id == id if id else text(""),
                Firmware.email.like("%" + email + "%") if email else text(""),
                Firmware.flash_size == flash_size if flash_size else text(""),
                Firmware.device_type == device_type if device_type else text("")
            )
        else:
            firmware = db.query(Firmware).order_by(Firmware.id.desc()).filter(
                Firmware.id == id if id else text(""),
                Firmware.email.like("%" + email + "%") if email else text(""),
                Firmware.flash_size == flash_size if flash_size else text(""),
                Firmware.device_type == device_type if device_type else text("")
            )
        try:
            total = firmware.count()
        except UnboundLocalError:
            total = 0

        try:
            items = firmware.offset((page - 1) * limit).limit(limit).all()
        except UnboundLocalError:
            items = []

        return {"data": {"items": items, "total": total}}
    except:
        lg.error(f"查询已编译固件列表异常：{traceback.format_exc()}")
        raise UnicornException(message="系统内部错误")
    finally:
        if hasattr(db, "close"):
            db.close()


@app.get("/download")
async def download_file(
        firmware_id: int = Query(..., title="固件ID"),
        retrieve_password: str = Query(None, title="提取密码", example=None),
        file_type: int = Query(..., title="文件类型,0/下载源代码 1/下载固件", glt=0, example=0),
        db: Session = Depends(get_db)
):
    try:
        firmware = db.query(Firmware).filter(Firmware.id == firmware_id).first()

        if firmware is None:
            raise UnicornException(code=404, message="固件不存在")

        # 有密码，但是没有输入密码
        if firmware.retrieve_password and not retrieve_password:
            raise UnicornException(code=5000, message="提取密码错误")

        # 有密码，但是输入密码错误
        if firmware.retrieve_password and firmware.retrieve_password != await sign_md5(retrieve_password):
            raise UnicornException(code=5000, message="提取密码错误")

        if file_type == 1:
            file_path = f"{APP_PATH}{firmware.firmware_file_path}"
            file_name = os.path.basename(file_path)
        else:
            file_path = f"{APP_PATH}{firmware.custom_source_code_file_path}"
            file_name = os.path.basename(file_path)

        # 判断文件是否存在
        if not os.path.exists(file_path):
            raise UnicornException(code=5000, message="文件不存在")
            # return FileResponse(file_path, media_type='application/octet-stream', filename=file_name)
        return FileResponse(file_path, headers={"Content-Disposition": f'attachment; filename="{file_name}"'})
    finally:
        if hasattr(db, "close"):
            db.close()

