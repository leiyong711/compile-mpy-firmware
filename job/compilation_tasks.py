# !/usr/bin/env python
# -*- coding:utf-8 -*-
"""串行处理固件编译队列，并持续记录可通过 WebSocket 读取的精确进度。"""

import os
import re
import shlex
import shutil
import traceback
import zipfile
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


OTA_PACKAGE_README = """MicroPython OTA 固件包（请先读）

1. firmware.bin
   完整固件，包含 bootloader、分区表和应用。首次安装或分区表改变时，
   必须通过 USB/串口按该开发板的官方烧录说明写入。

2. ota-application.bin
   仅应用镜像，供设备已经运行 OTA 版固件后写入备用 ota_0/ota_1 分区。
   不要把 firmware.bin 整包写进 OTA 应用分区。

重要说明：选择 OTA 只建立双应用分区，并不会自动完成网络下载、SHA-256/
签名校验、断电保护、切换启动或回滚确认。完整流程和安全注意事项请打开
Web 页面 /help/variants 查看。
"""


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


def _save_firmware_artifact(
    build_dir: Path,
    output_dir: Path,
    board_variant: str,
    ota_partition_size: int = None,
) -> Path:
    """保存可下载产物；OTA 同时提供首次烧录包和后续升级应用镜像。"""
    firmware_bin = build_dir / "firmware.bin"
    if not firmware_bin.is_file():
        raise RuntimeError(f"编译日志成功，但未找到固件：{firmware_bin}")

    if board_variant != "OTA":
        destination = output_dir / firmware_bin.name
        shutil.copy2(firmware_bin, destination)
        return destination

    application_bin = build_dir / "micropython.bin"
    if not application_bin.is_file():
        raise RuntimeError(f"OTA 编译成功，但未找到应用镜像：{application_bin}")
    if ota_partition_size is None:
        raise RuntimeError("无法确定 OTA 应用分区容量，拒绝生成不可验证的升级包")
    application_size = application_bin.stat().st_size
    if application_size > ota_partition_size:
        raise RuntimeError(
            "OTA 应用镜像超出分区容量："
            f"镜像 {application_size} 字节，分区 {ota_partition_size} 字节"
        )
    destination = output_dir / "firmware-ota-package.zip"
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(firmware_bin, "firmware.bin")
        archive.write(application_bin, "ota-application.bin")
        archive.writestr("OTA流程说明.txt", OTA_PACKAGE_README)
    return destination


def _partition_size(value: str) -> int:
    """解析 ESP-IDF 分区表中的十六进制、十进制和 K/M 大小。"""
    text = value.strip().upper()
    multiplier = 1
    if text.endswith("K"):
        multiplier, text = 1024, text[:-1]
    elif text.endswith("M"):
        multiplier, text = 1024 * 1024, text[:-1]
    return int(text, 0) * multiplier


def _ota_partition_capacity(port_dir: Path, selection) -> int:
    """从本次实际板级 sdkconfig 与 CSV 读取 ota_0/ota_1 的最小容量。"""
    board_dir = port_dir / "boards" / selection.effective_board
    native_config_name = (
        f"sdkconfig.{selection.effective_variant.lower()}"
        if selection.effective_variant
        else "sdkconfig.board"
    )
    config_paths = [board_dir / "sdkconfig.web", board_dir / native_config_name]
    match = None
    matched_config = None
    for config_path in config_paths:
        if not config_path.is_file():
            continue
        candidate = re.search(
            r'^CONFIG_PARTITION_TABLE_CUSTOM_FILENAME="([^"]+)"$',
            config_path.read_text(encoding="utf-8"),
            re.MULTILINE,
        )
        if candidate:
            match = candidate
            matched_config = config_path
            break
    if not match:
        raise RuntimeError(
            "OTA 配置没有指定自定义分区表："
            + ", ".join(str(path) for path in config_paths)
        )
    partition_path = port_dir / match.group(1)
    if not partition_path.is_file():
        raise RuntimeError(
            f"找不到 OTA 分区表：{partition_path}（来自 {matched_config}）"
        )

    capacities = []
    for raw_line in partition_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        columns = [column.strip() for column in line.split(",")]
        if (
            len(columns) >= 5
            and columns[1] == "app"
            and columns[2] in ("ota_0", "ota_1")
        ):
            capacities.append(_partition_size(columns[4]))
    if len(capacities) != 2:
        raise RuntimeError(f"分区表必须同时包含 ota_0 和 ota_1：{partition_path}")
    return min(capacities)


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
        ota_partition_size = (
            _ota_partition_capacity(port_dir, selection)
            if selection.board_variant == "OTA"
            else None
        )
        firmware_artifact = _save_firmware_artifact(
            build_dir,
            output_dir,
            selection.board_variant,
            ota_partition_size=ota_partition_size,
        )
        shutil.copy2(source_archive, output_dir / source_archive.name)

        firmware = Firmware(
            email=task.email,
            device_type=selection.device_type,
            flash_size=selection.flash_size,
            board=selection.board,
            board_variant=selection.board_variant,
            firmware_file_path=f"{relative_output}/{firmware_artifact.name}",
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
        lg.info("任务 {} 编译成功：{}", task_id, firmware_artifact)

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
