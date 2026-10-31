# !/usr/bin/env python
# -*- coding:utf-8 -*-
"""串行处理固件编译队列，并持续记录可通过 WebSocket 读取的精确进度。"""

import os
import shlex
import shutil
import traceback
from datetime import datetime
from pathlib import Path

from app.v1.firmware.build_options import validate_selection
from app.v1.firmware.db_model import Firmware, FirmwareWaitCompiled, SessionLocal
from job.build_progress import (
    BuildOutputParser,
    estimate_esp8266_steps,
    run_streaming_command,
    set_progress,
)
from utils.config import Config
from utils.constants import RUNTIME_PATH
from utils.log import lg
from utils.tools import compress_folder, decompress_folder, find_dirs


config = Config()


def _shell_environment(device_type: str) -> str:
    profile = "if [ -f ~/.profile ]; then . ~/.profile; fi"
    if device_type == "ESP8266":
        fallback = os.getenv("ESP8266_SDK_ROOT", "/opt/esp-open-sdk/xtensa-lx106-elf")
        idf_tools = os.getenv("IDF_TOOLS_PATH", "/root/.espressif")
        esptool_bin = f"{idf_tools}/python_env/idf5.0_py3.9_env/bin"
        setup = (
            "if declare -F get_esp8266 >/dev/null 2>&1; then get_esp8266; "
            f"else export ESP_SDK={shlex.quote(fallback + '/xtensa-lx106-elf/sysroot/usr')}; "
            "export CFLAGS_EXTRA=-Wno-error; "
            f"export PATH={shlex.quote(esptool_bin)}:{shlex.quote(fallback + '/bin')}:$PATH; fi"
        )
    else:
        export_script = os.getenv("ESP_IDF_EXPORT", "/opt/esp-idf-v5.0.4/export.sh")
        setup = (
            "if declare -F get_idf_5_0_4 >/dev/null 2>&1; then get_idf_5_0_4; "
            f"elif [ -f {shlex.quote(export_script)} ]; then . {shlex.quote(export_script)} >/dev/null; "
            "else echo '找不到 ESP-IDF 环境' >&2; exit 2; fi"
        )
    return f"{profile}; {setup}"


def _make_command(directory: Path, make_arguments, jobs: int, dry_run: bool = False) -> str:
    arguments = " ".join(shlex.quote(value) for value in make_arguments)
    dry = "-n " if dry_run else ""
    return f"cd {shlex.quote(str(directory))}; make {dry}-j{jobs} {arguments}".rstrip()


def _build_dir_name(board: str, variant: str) -> str:
    return f"build-{board}" + (f"-{variant}" if variant else "")


def _remove_build_directories(port_dir: Path) -> None:
    for build_path in find_dirs(str(port_dir), "build*", 0):
        try:
            shutil.rmtree(build_path)
        except OSError:
            lg.exception("删除历史编译目录失败：{}", build_path)


def compilation_tasks(text=""):
    lg.info(text)
    session = SessionLocal()
    task = None
    modules_dir = None
    modules_backup = None
    port_dir = None

    try:
        if session.query(FirmwareWaitCompiled).filter(FirmwareWaitCompiled.status == 2).first():
            lg.debug("已有任务正在编译，本轮结束")
            return

        # 失败任务保留给用户查看，不自动无限重试；重新上传会创建新任务。
        task = (
            session.query(FirmwareWaitCompiled)
            .filter(FirmwareWaitCompiled.status == 3)
            .order_by(FirmwareWaitCompiled.create_time)
            .first()
        )
        if task is None:
            lg.debug("没有需要编译的数据，本轮结束")
            return

        task.status = 2
        task.update_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        session.commit()
        set_progress(task.id, 1, "preparing", "正在校验编译参数")

        micropython_dir = Path(
            os.getenv("MICROPYTHON_DIR")
            or config.get_jsonpath("$.ProjectConfig.micropython_dir")
        ).resolve()
        if not micropython_dir.is_dir():
            raise RuntimeError(f"MicroPython 目录不存在：{micropython_dir}")

        selection = validate_selection(
            task.device_type,
            task.flash_size,
            task.board or "",
            task.board_variant or "",
            micropython_dir=micropython_dir,
            prepare_board=True,
        )
        # 兼容旧数据库中的 ESP32_S、2M 等历史值。
        task.device_type = selection.device_type
        task.flash_size = selection.flash_size
        task.board = selection.board
        task.board_variant = selection.board_variant
        session.commit()

        port_name = "esp8266" if selection.device_type == "ESP8266" else "esp32"
        port_dir = micropython_dir / "ports" / port_name
        modules_dir = port_dir / "modules"
        modules_backup = port_dir / "modules.zip"
        if not modules_dir.is_dir():
            if not modules_backup.is_file():
                raise RuntimeError(f"{modules_dir} 和备份 {modules_backup} 均不存在")
            decompress_folder(str(modules_backup), str(modules_dir))

        set_progress(task.id, 3, "preparing", "正在备份内置 modules")
        compress_folder(str(modules_dir), str(modules_dir))
        source_archive = Path(RUNTIME_PATH + task.custom_source_code_file_path)
        if not source_archive.is_file():
            raise RuntimeError(f"上传源码不存在：{source_archive}")
        decompress_folder(str(source_archive), str(modules_dir))

        _remove_build_directories(port_dir)
        jobs = max(1, int(os.getenv("BUILD_JOBS", os.cpu_count() or 2)))
        environment = _shell_environment(selection.device_type)

        set_progress(task.id, 5, "mpy-cross", "正在准备 mpy-cross")
        cross_command = (
            f"{environment}; "
            + _make_command(micropython_dir / "mpy-cross", [], jobs)
        )
        status, cross_output = run_streaming_command(
            cross_command,
            timeout_seconds=min(
                600, int(config.get_jsonpath("$.ProjectConfig.build_timeout_seconds", 1800))
            ),
        )
        if not status:
            raise RuntimeError(f"mpy-cross 编译失败：\n{cross_output[-8000:]}")

        make_arguments = selection.make_arguments
        total_steps = 0
        if selection.device_type == "ESP8266":
            dry_command = f"{environment}; " + _make_command(
                port_dir, make_arguments, jobs, dry_run=True
            )
            total_steps = estimate_esp8266_steps(dry_command)

        set_progress(task.id, 10, "building", "正在编译 MicroPython 固件")
        parser = BuildOutputParser(task.id, selection.device_type, total_steps)
        build_command = f"{environment}; " + _make_command(port_dir, make_arguments, jobs)
        build_timeout = int(
            config.get_jsonpath("$.ProjectConfig.build_timeout_seconds", 1800)
        )
        compilation_start_time = datetime.now()
        status, build_output = run_streaming_command(
            build_command,
            timeout_seconds=build_timeout,
            on_line=parser.feed,
        )
        if not status:
            raise RuntimeError(f"固件编译失败：\n{build_output[-12000:]}")

        build_dir = port_dir / _build_dir_name(
            selection.effective_board, selection.effective_variant
        )
        bin_file = build_dir / "firmware.bin"
        if not bin_file.is_file():
            raise RuntimeError(f"编译日志成功，但未找到固件：{bin_file}")

        set_progress(task.id, 96, "packaging", "正在保存固件和源码包")
        total_time_spent = int(
            (datetime.now() - compilation_start_time).total_seconds() * 1000
        )
        after_dir = config.get_jsonpath(
            "$.ProjectConfig.after_compilation_dir", "/res_pack/after_compilation"
        )
        firmware_folder = task.email.replace("@", "_at_").replace(".", "_dot_")
        upload_name = Path(task.custom_source_code_file_path).stem
        relative_output = f"{after_dir}/{firmware_folder}/{upload_name}"
        output_dir = Path(RUNTIME_PATH + relative_output)
        output_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(bin_file, output_dir / bin_file.name)
        shutil.copy2(source_archive, output_dir / source_archive.name)

        firmware = Firmware(
            email=task.email,
            device_type=selection.device_type,
            flash_size=selection.flash_size,
            board=selection.board,
            board_variant=selection.board_variant,
            firmware_file_path=f"{relative_output}/{bin_file.name}",
            custom_source_code_file_path=f"{relative_output}/{source_archive.name}",
            remark=task.remark,
            compilation_time_consuming=total_time_spent,
            retrieve_password=task.retrieve_password,
            upload_time=task.update_time,
            start_compilation_time=compilation_start_time.strftime("%Y-%m-%d %H:%M:%S"),
        )
        session.add(firmware)
        if source_archive.exists():
            source_archive.unlink()
        task_id = task.id
        session.delete(task)
        session.commit()
        set_progress(task_id, 100, "completed", "编译成功，固件可以下载", status="success")
        lg.info("任务 {} 编译成功：{}", task_id, bin_file)

    except Exception:
        error = traceback.format_exc()
        session.rollback()
        if task is not None:
            try:
                task.status = 1
                task.err_log = error
                task.update_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                session.commit()
                set_progress(
                    task.id,
                    100,
                    "failed",
                    error.strip().splitlines()[-1],
                    status="failed",
                )
            except Exception:
                session.rollback()
        lg.error("定时编译失败：\n{}", error)
    finally:
        # 无论成功失败都恢复干净的 modules，避免不同用户源码相互污染。
        if modules_dir and modules_backup and modules_backup.is_file():
            try:
                if modules_dir.exists():
                    shutil.rmtree(modules_dir)
                decompress_folder(str(modules_backup), str(modules_dir))
            except Exception:
                lg.exception("恢复 modules 失败")
        if port_dir:
            _remove_build_directories(port_dir)
        session.close()


if __name__ == "__main__":
    compilation_tasks("手动执行编译任务")
