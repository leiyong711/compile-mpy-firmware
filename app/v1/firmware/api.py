# !/usr/bin/env python
# -*- coding:utf-8 -*-
# project name: compile-mpy-firmware
# author: "Lei Yong" 
# creation time: 2023-11-28 20:03
# Email: leiyong711@163.com

import asyncio
import datetime
import hashlib
import io
import os
import shutil
import traceback
import threading
import zipfile
from pathlib import Path
from utils.log import lg
from utils.config import Config
from utils.constants import RUNTIME_PATH
from utils.tools import generate_random_number, compress_folder, sign_md5
from utils.exception_handling import *
from typing import List
from .build_options import (
    discover_build_options,
    normalize_device_type,
    normalize_flash_size,
    validate_selection,
)
from .db_model import Firmware, FirmwareBuildProgress, FirmwareWaitCompiled, text
from .api_model import CreateCompilationTaskOUT, GetFirmwareListOut, GetFirmwareWaitCompiledListOut
from dbs.sqlite_connect import SessionLocal, Session
from fastapi import APIRouter, Request, File, UploadFile, Form, Depends, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response, JSONResponse, StreamingResponse
from job.build_progress import get_progress, set_progress
# from fastapi.responses import JSONRespons


app = APIRouter()
config = Config()


async def _check_firmware_password(firmware, retrieve_password: str):
    """统一校验固件下载密码。OTA 接口和普通下载使用同一规则。"""
    if firmware.retrieve_password and not retrieve_password:
        raise UnicornException(code=5000, message="提取密码错误")
    if (
        firmware.retrieve_password
        and firmware.retrieve_password != await sign_md5(retrieve_password)
    ):
        raise UnicornException(code=5000, message="提取密码错误")


def _read_ota_application(firmware):
    """从平台生成的 OTA 固件包读取应用镜像并计算可信元数据。"""
    if firmware.board_variant != "OTA":
        raise UnicornException(code=4000, message="该记录不是 OTA 固件")
    package_path = f"{RUNTIME_PATH}{firmware.firmware_file_path}"
    if not os.path.isfile(package_path):
        raise UnicornException(code=5000, message="OTA 固件包不存在")
    try:
        with zipfile.ZipFile(package_path) as package:
            application = package.read("ota-application.bin")
    except (KeyError, zipfile.BadZipFile):
        raise UnicornException(code=5000, message="OTA 固件包损坏或缺少应用镜像")
    return application, hashlib.sha256(application).hexdigest()


# 依赖函数，用于获取数据库会话
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/build-options", summary="获取当前环境可用的芯片、开发板和编译参数")
async def get_build_options():
    return {"code": 2000, "status": True, "message": "success", "data": discover_build_options()}


@app.get("/progress/{task_id}", summary="查询编译进度")
async def get_build_progress(task_id: int):
    progress = get_progress(task_id)
    if progress is None:
        raise UnicornException(code=404, message="编译任务不存在")
    return {"code": 2000, "status": True, "message": "success", "data": progress}


def _task_source_archive(task: FirmwareWaitCompiled) -> Path:
    """解析任务源码包，并限定它必须位于上传目录内。"""
    runtime_root = Path(RUNTIME_PATH).resolve()
    upload_dir = config.get_jsonpath("$.ProjectConfig.upload_dir", "/res_pack/upload")
    upload_root = (runtime_root / str(upload_dir).lstrip("/\\")).resolve()
    archive = (
        runtime_root / str(task.custom_source_code_file_path).lstrip("/\\")
    ).resolve()
    try:
        archive.relative_to(upload_root)
    except ValueError:
        raise UnicornException(code=4000, message="任务源码路径不安全，拒绝操作")
    if archive.suffix.lower() != ".zip":
        raise UnicornException(code=4000, message="任务源码不是 ZIP 文件，拒绝操作")
    return archive


@app.post("/tasks/{task_id}/retry", summary="重试失败的编译任务")
async def retry_compilation_task(task_id: int, db: Session = Depends(get_db)):
    """使用原任务的源码和参数重新入队，不会创建重复记录。"""
    task = db.query(FirmwareWaitCompiled).filter_by(id=task_id).first()
    if task is None:
        raise UnicornException(code=404, message="编译任务不存在")
    if task.status != 1:
        raise UnicornException(code=4000, message="只有编译失败的任务可以重试")

    source_archive = _task_source_archive(task)
    if not source_archive.is_file():
        raise UnicornException(
            code=4000,
            message="原始源码包已不存在，请在“新建编译任务”中重新上传",
        )

    task.status = 3
    task.err_log = None
    task.update_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.commit()
    set_progress(task.id, 0, "queued", "用户已重试，任务正在排队", status="queued")
    return {
        "code": 2000,
        "status": True,
        "message": "任务已重新进入编译队列",
        "data": {"id": task.id},
    }


@app.delete("/tasks/{task_id}", summary="删除编译队列任务")
async def delete_compilation_task(task_id: int, db: Session = Depends(get_db)):
    """删除失败/排队任务，并清理对应进度和上传的源码包。"""
    task = db.query(FirmwareWaitCompiled).filter_by(id=task_id).first()
    if task is None:
        raise UnicornException(code=404, message="编译任务不存在")
    if task.status == 2:
        raise UnicornException(code=4000, message="任务正在编译，不能直接删除")
    if task.status not in (1, 3):
        raise UnicornException(code=4000, message="当前任务状态不允许删除")

    source_archive = _task_source_archive(task)
    progress = db.query(FirmwareBuildProgress).filter_by(task_id=task_id).first()
    if progress is not None:
        db.delete(progress)
    db.delete(task)
    db.commit()

    if source_archive.is_file():
        try:
            source_archive.unlink()
        except OSError:
            lg.exception("任务已删除，但清理源码包失败：{}", source_archive)
    return {
        "code": 2000,
        "status": True,
        "message": "任务、进度记录和源码包已删除",
        "data": {"id": task_id},
    }


@app.websocket("/ws/progress/{task_id}")
async def progress_websocket(websocket: WebSocket, task_id: int):
    """进度落库后再推送，刷新页面或多进程部署都不会丢状态。"""
    await websocket.accept()
    last_payload = None
    try:
        while True:
            progress = get_progress(task_id)
            if progress is None:
                payload = {
                    "task_id": task_id,
                    "percentage": 0,
                    "stage": "unknown",
                    "message": "编译任务不存在",
                    "status": "failed",
                    "current_step": 0,
                    "total_steps": 0,
                }
            else:
                if progress.get("updated_at"):
                    progress["updated_at"] = progress["updated_at"].isoformat()
                payload = progress

            signature = (
                payload.get("percentage"),
                payload.get("stage"),
                payload.get("message"),
                payload.get("status"),
            )
            if signature != last_payload:
                await websocket.send_json(payload)
                last_payload = signature
            if payload.get("status") in ("success", "failed"):
                await websocket.close(code=1000)
                return
            await asyncio.sleep(0.35)
    except WebSocketDisconnect:
        return


@app.post("/upload", tags=[], summary="创建编译任务", response_model=CreateCompilationTaskOUT, responses={422: {'model': ErrorOUt}})
async def upload_file(
        files: List[UploadFile] = File(..., title="待编译固件文件"),
        device_type: str = Form(..., title="设备类型"),
        flash_size: str = Form(..., title="Flash大小"),
        board: str = Form('', title="开发板"),
        board_variant: str = Form('', title="开发板变体"),
        email: str = Form(..., title="邮箱"),
        password: str = Form('', title="提取密码"),
        remark: str = Form('', title="备注"),
        db: Session = Depends(get_db)
):
    filename_dir = generate_random_number()
    upload_dir = config.get_jsonpath("ProjectConfig.upload_dir", 'upload')
    temporary_folder = f"{RUNTIME_PATH}{upload_dir}/{filename_dir}"
    try:

        try:
            selection = validate_selection(device_type, flash_size, board, board_variant)
        except ValueError as exc:
            raise UnicornException(code=4000, message=str(exc))

        if not os.path.exists(temporary_folder):
            os.makedirs(temporary_folder)

        for file in files:
            # 获取文件的原始文件名
            filename = os.path.basename(file.filename or "")
            if not filename:
                raise UnicornException(code=4000, message="上传文件名不能为空")
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
            "device_type": selection.device_type,
            "flash_size": selection.flash_size,
            "board": selection.board,
            "board_variant": selection.board_variant,
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
        set_progress(new_instance_id, 0, "queued", "任务已进入编译队列", status="queued")

        # lg.debug(f"收到文件：{files}\t设备: {device_type}\t大小: {flash_size}\t邮箱：{email}\t密码：{password}\t备注：{remark}")
        return {"data": {"id": new_instance_id, "msg": "创建编译任务成功"}}
    except UnicornException:
        raise
    except Exception:
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

    flash_size = None if flash_size in (None, "", "all") else normalize_flash_size(flash_size)
    device_type = None if device_type in (None, "", "all") else normalize_device_type(device_type)

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

    flash_size = None if flash_size in (None, "", "all") else normalize_flash_size(flash_size)
    device_type = None if device_type in (None, "", "all") else normalize_device_type(device_type)

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
        file_type: int = Query(..., title="文件类型,0/下载源代码 1/下载固件", ge=0, le=1, example=0),
        db: Session = Depends(get_db)
):
    try:
        firmware = db.query(Firmware).filter(Firmware.id == firmware_id).first()

        if firmware is None:
            raise UnicornException(code=404, message="固件不存在")

        await _check_firmware_password(firmware, retrieve_password)

        if file_type == 1:
            file_path = f"{RUNTIME_PATH}{firmware.firmware_file_path}"
            file_name = os.path.basename(file_path)
        else:
            file_path = f"{RUNTIME_PATH}{firmware.custom_source_code_file_path}"
            file_name = os.path.basename(file_path)

        # 判断文件是否存在
        if not os.path.exists(file_path):
            raise UnicornException(code=5000, message="文件不存在")
            # return FileResponse(file_path, media_type='application/octet-stream', filename=file_name)
        return FileResponse(file_path, headers={"Content-Disposition": f'attachment; filename="{file_name}"'})
    finally:
        if hasattr(db, "close"):
            db.close()


@app.get("/ota/{firmware_id}/manifest", summary="获取 OTA 应用镜像元数据")
async def get_ota_manifest(
        firmware_id: int,
        retrieve_password: str = Query(None, title="提取密码"),
        db: Session = Depends(get_db)):
    """返回设备端更新前必须核对的大小和 SHA-256。"""
    firmware = db.query(Firmware).filter(Firmware.id == firmware_id).first()
    if firmware is None:
        raise UnicornException(code=404, message="固件不存在")
    await _check_firmware_password(firmware, retrieve_password)
    application, sha256 = _read_ota_application(firmware)
    return {
        "code": 2000,
        "status": True,
        "message": "success",
        "data": {
            "firmware_id": firmware.id,
            "device_type": firmware.device_type,
            "board": firmware.board,
            "board_variant": firmware.board_variant,
            "size": len(application),
            "sha256": sha256,
            "download_path": f"/api/ota/{firmware.id}/application.bin",
        },
    }


@app.get("/ota/{firmware_id}/application.bin", summary="下载 OTA 应用镜像")
async def download_ota_application(
        firmware_id: int,
        retrieve_password: str = Query(None, title="提取密码"),
        db: Session = Depends(get_db)):
    """供设备流式下载；只返回 ota-application.bin，不返回完整烧录镜像。"""
    firmware = db.query(Firmware).filter(Firmware.id == firmware_id).first()
    if firmware is None:
        raise UnicornException(code=404, message="固件不存在")
    await _check_firmware_password(firmware, retrieve_password)
    application, sha256 = _read_ota_application(firmware)
    return Response(
        content=application,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": 'attachment; filename="ota-application.bin"',
            "X-OTA-SHA256": sha256,
            "Cache-Control": "no-store",
        },
    )

