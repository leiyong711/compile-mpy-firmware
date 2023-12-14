# !/usr/bin/env python
# -*- coding:utf-8 -*-
# project name: compile-mpy-firmware
# author: "Lei Yong" 
# creation time: 2023-12-13 14:37
# Email: leiyong711@163.com

import os
import re
import shutil
import traceback
from pathlib import Path
from sqlalchemy import desc
from datetime import datetime
from utils.log import lg
from utils.tools import compress_folder, decompress_folder, find_files, find_dirs, excuting_command
from utils.config import Config
from utils.constants import APP_PATH
from app.v1.firmware.db_model import Firmware, FirmwareWaitCompiled, SessionLocal

config = Config()


# 依赖函数，用于获取数据库会话
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def compilation_tasks(text=""):
    """编译任务"""
    lg.info(text)
    session = next(get_db())
    micropython_dir = ""
    device_dir = ""
    try:
        # 正在编译的数据
        data_being_compiled = session.query(FirmwareWaitCompiled).filter(FirmwareWaitCompiled.status == 2).order_by(FirmwareWaitCompiled.update_time).all()

        # 有正在编译的任务，直接返回
        if data_being_compiled:
            lg.debug(f"有正在编译的任务，直接结束本次任务")
            return

        # 为等待编译的数据创建查询
        waiting_query = session.query(FirmwareWaitCompiled).filter(FirmwareWaitCompiled.status == 3).order_by(FirmwareWaitCompiled.create_time)
        # 没有待编译数据，则为编译失败的数据创建查询
        if waiting_query.count() == 0:
            # 为编译失败的数据创建查询
            waiting_query = session.query(FirmwareWaitCompiled).filter(FirmwareWaitCompiled.status == 1).order_by(FirmwareWaitCompiled.update_time)

        # 没有需要编译的数据，则直接返回
        if waiting_query.count() == 0:
            lg.debug(f"没有需要编译的数据，直接结束本次任务")
            return

        # 获取结果
        first_result = waiting_query.first()

        # 修改状态和更新时间
        first_result.status = 2  # 假设2代表"编译中"# 编译状态,0:编译成功,1:编译失败,2:编译中,3:等待编译
        first_result.update_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # 更新时间为当前时间

        # 提交更改
        session.commit()
        try:
            # 开始编译时间
            devices = first_result.device_type

            # 获取micropython目录
            micropython_dir = config.get_jsonpath('$.ProjectConfig.micropython_dir')
            if not micropython_dir:
                raise Exception("micropython目录不存在")

            # 备份modules
            device_dir = ""
            if devices == "ESP8266":
                device_dir = config.get_jsonpath('$.ProjectConfig.esp8266_dir')
                if not device_dir:
                    raise Exception("esp8266目录不存在")

            elif devices == "ESP32":
                device_dir = config.get_jsonpath('$.ProjectConfig.esp32_dir')
                if not device_dir:
                    raise Exception("esp32目录不存在")

            # 检查device_dir文件夹是否存在
            if not os.path.exists(f"{micropython_dir}{device_dir}/modules"):
                # 检查备份zip文件是否存在
                if not os.path.exists(f"{micropython_dir}{device_dir}/modules.zip"):
                    raise Exception(f"{micropython_dir}{device_dir}/modules文件夹不存在,且modules.zip文件不存在")

                # 解压备份文件
                lg.info(f"{micropython_dir}{device_dir}文件夹不存在，解压备份文件")
                decompress_folder(f"{micropython_dir}{device_dir}/modules.zip", f"{micropython_dir}{device_dir}/modules")

            # 备份modules
            lg.debug(f"备份modules")
            compress_folder(f"{micropython_dir}{device_dir}/modules", f"{micropython_dir}{device_dir}/modules")

            # 解压自定义源码文件
            lg.debug(f"解压自定义源码文件")
            decompress_folder(f"{APP_PATH}{first_result.custom_source_code_file_path}", f"{micropython_dir}{device_dir}/modules")

            # 删除历史编译的文件目录
            matches = find_dirs(f"{micropython_dir}{device_dir}", "build*", 0)
            for build_path in matches:
                lg.warning(f"删除历史编译的文件目录 {build_path}")
                try:
                    shutil.rmtree(build_path)
                except:
                    ...

            if devices == "ESP8266":
                # command = f"/bin/bash -i -c get_esp8266  && cd {micropython_dir} && make -C mpy-cross && cd ports/esp8266 && make"
                # 定义 ESP8266 命令
                commands = [
                    "get_esp8266",
                    f"cd {micropython_dir}",
                    "make -C mpy-cross",
                    "cd ports/esp8266",
                    "make"
                ]

            elif devices == "ESP32":
                # 定义 ESP32 命令
                commands = [
                    "get_esp32",
                    f"cd {micropython_dir}",
                    "make -C mpy-cross",
                    "cd ports/esp32",
                    "make submodules",
                    # "make BOARD=ESP32_GENERIC_C3"
                ]

            # 创建一个新的 shell 脚本文件
            with open(f"{APP_PATH}/build_script.sh", "w") as file:
                file.write("#!/bin/bash\n")
                for command in commands:
                    file.write(command + "\n")
            command = f"sh {APP_PATH}/build_script.sh"

            # 编译开始时间
            compilation_start_time = datetime.now()

            status, result = excuting_command(command, timeout_seconds=300)

            if not status:
                lg.error(f"编译失败，原因：{result}")
                raise Exception(f"编译失败")

            # 搜索目标字符串
            if "_GENERIC/firmware.bin" not in result:
                lg.error(f"编译失败，原因：{result}")
                raise Exception(f"编译失败")

            bin_file_name = re.findall(r"Create (.*?)\.bin", result)
            if not bin_file_name:
                lg.error(f"编译失败，原因：编译信息中未找到bin文件")
                raise Exception(f"编译失败，原因：编译信息中未找到bin文件")

            bin_file_name = f"{micropython_dir}{device_dir}/{bin_file_name[0]}.bin" # bin文件路径

            if not os.path.exists(bin_file_name):
                lg.error(f"编译失败，原因：未在{bin_file_name}中找到bin文件")
                raise Exception(f"编译失败，原因：未在{bin_file_name}中找到bin文件")

            lg.debug(f"编译成功")
            # 总耗时
            total_time_spent = int((datetime.now() - compilation_start_time).total_seconds() * 1000)

            # 固件文件夹名称
            after_compilation_dir = config.get_jsonpath("ProjectConfig.after_compilation_dir", "/res_pack/after_compilation_dir") # 编译后的文件夹名称
            firmware_folder_name = first_result.email.replace("@", "_at_").replace(".", "_dot_")    # 邮箱作为文件夹名称
            file_name = Path(first_result.custom_source_code_file_path).stem                        # 上传的文件名

            # 创建文件夹
            compile_content_file_path = f"{after_compilation_dir}/{firmware_folder_name}/{file_name}"
            if not os.path.exists(f"{APP_PATH}{compile_content_file_path}"):
                os.makedirs(f"{APP_PATH}{compile_content_file_path}")

            # 复制编译后的文件
            shutil.copy(bin_file_name, f"{APP_PATH}{compile_content_file_path}")

            # 复制上传的源代码压缩包
            shutil.copy(f"{APP_PATH}{first_result.custom_source_code_file_path}", f"{APP_PATH}{compile_content_file_path}")

            # 插入数据库
            params = {
                "email": first_result.email,                     # 邮箱
                "device_type": first_result.device_type,         # 设备类型
                "flash_size": first_result.flash_size,       # Flash大小
                "firmware_file_path": f"{compile_content_file_path}/{Path(bin_file_name).name}",  # 固件文件路径
                "custom_source_code_file_path": f"{compile_content_file_path}/{Path(first_result.custom_source_code_file_path).name}",      # 自定义源码文件路径
                "remark": first_result.remark,               # 备注
                "compilation_time_consuming": total_time_spent,  # 编译耗时
                "retrieve_password": first_result.retrieve_password,  # 提取密码
                "upload_time": first_result.update_time,  # 上传时间
                "start_compilation_time": f"{compilation_start_time.strftime('%Y-%m-%d %H:%M:%S')}",  # 开始编译时间
            }

            new_instance = Firmware(**params)
            session.add(new_instance)
            session.commit()
            session.refresh(new_instance)

            # 删除编译成功的数据
            if os.path.exists(f"{APP_PATH}{first_result.custom_source_code_file_path}"):
                os.remove(f"{APP_PATH}{first_result.custom_source_code_file_path}")
                lg.debug(f"编译成功，删除原来的数据")

            # 删除原来的数据
            session.delete(first_result)

            # 提交更改
            session.commit()
        except:
            # 修改状态和更新时间
            first_result.status = 1
            session.commit()
            lg.error(f"定时编译失败，原因: \n{traceback.format_exc()}")
    except:
        lg.error(f"定时编译失败，原因: \n{traceback.format_exc()}")
    finally:
        if hasattr(session, "close"):
            session.close()

        # 恢复modules
        if micropython_dir and device_dir:
            lg.debug(f"恢复modules")
            try:
                shutil.rmtree(f"{micropython_dir}{device_dir}/modules")
            except:
                lg.error(f"删除modules文件夹失败,原因:\n{traceback.format_exc()}")


if __name__ == '__main__':
    compilation_tasks()
    # backup_modules()
