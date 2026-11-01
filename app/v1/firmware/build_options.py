"""MicroPython 编译目标、开发板、变体与 Flash 参数的统一定义。"""

import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from utils.config import Config


DEVICE_LABELS = {
    "ESP8266": "ESP8266",
    "ESP32": "ESP32",
    "ESP32_S2": "ESP32-S2",
    "ESP32_S3": "ESP32-S3",
    "ESP32_C2": "ESP32-C2 / ESP8684",
    "ESP32_C3": "ESP32-C3",
    "ESP32_C5": "ESP32-C5",
    "ESP32_C6": "ESP32-C6",
    "ESP32_H2": "ESP32-H2",
    "ESP32_P4": "ESP32-P4",
}

MCU_TO_DEVICE = {
    "esp8266": "ESP8266",
    "esp32": "ESP32",
    "esp32s2": "ESP32_S2",
    "esp32s3": "ESP32_S3",
    "esp32c2": "ESP32_C2",
    "esp32c3": "ESP32_C3",
    "esp32c5": "ESP32_C5",
    "esp32c6": "ESP32_C6",
    "esp32h2": "ESP32_H2",
    "esp32p4": "ESP32_P4",
}

DEFAULT_BOARDS = {
    "ESP8266": "ESP8266_GENERIC",
    "ESP32": "ESP32_GENERIC",
    "ESP32_S2": "ESP32_GENERIC_S2",
    "ESP32_S3": "ESP32_GENERIC_S3",
    "ESP32_C2": "ESP32_GENERIC_C2",
    "ESP32_C3": "ESP32_GENERIC_C3",
    "ESP32_C5": "ESP32_GENERIC_C5",
    "ESP32_C6": "ESP32_GENERIC_C6",
    "ESP32_H2": "ESP32_GENERIC_H2",
    "ESP32_P4": "ESP32_GENERIC_P4",
}

ESP_FLASH_SIZES = ["AUTO", "2MB", "4MB", "8MB", "16MB"]
ESP8266_FLASH_SIZES = ["512KB", "1MB", "2MB"]
FLASH_ALIASES = {
    "AUTO": "AUTO",
    "512K": "512KB",
    "512KB": "512KB",
    "1M": "1MB",
    "1MB": "1MB",
    "2M": "2MB",
    "2MB": "2MB",
    "4M": "4MB",
    "4MB": "4MB",
    "8M": "8MB",
    "8MB": "8MB",
    "16M": "16MB",
    "16MB": "16MB",
}

ESP8266_FLASH_VARIANTS = {
    "512KB": "FLASH_512K",
    "1MB": "FLASH_1M",
    "2MB": "",
}

# MicroPython v1.22.2 的 ESP32_GENERIC_C3 没有在 board.json 中声明 OTA
# variant，但 ESP32-C3/ESP-IDF 本身支持 OTA。平台为这个经过实机验证的通用板
# 生成独立 WEB_* 板级配置，不修改上游源码板，也不向其他未验证板型虚构选项。
PLATFORM_OTA_BOARDS = {"ESP32_GENERIC_C3"}

C3_OTA_PARTITION_FILE = "partitions-4MiB-ota-c3.csv"
C3_OTA_PARTITIONS = """# ESP32-C3 4MiB OTA partition table
# Name,   Type, SubType, Offset,   Size,     Flags
nvs,      data, nvs,     0x9000,   0x4000,
otadata,  data, ota,     0xd000,   0x2000,
phy_init, data, phy,     0xf000,   0x1000,
ota_0,    app,  ota_0,   0x10000,  0x1a0000,
ota_1,    app,  ota_1,   0x1b0000, 0x1a0000,
vfs,      data, fat,     0x350000, 0x0b0000,
"""


# 这些说明会随 /api/build-options 返回，前端因此能解释当前源码真正提供的
# variant，而不需要再维护一份容易过期的硬编码设备列表。
VARIANT_GUIDANCE = {
    "SPIRAM": {
        "name": "SPIRAM / PSRAM（外部内存）",
        "summary": "为带 Quad-SPI PSRAM 的 ESP32（常见于 WROVER 模组）启用外部内存支持，可扩大 MicroPython 可用堆。",
        "warning": "它增加的是运行内存，不是 Flash。普通 WROOM/无 PSRAM 开发板不要选择。",
        "beginner_choice": "只有开发板或模组规格明确写有 PSRAM/WROVER 时才选；不确定就用标准版。",
    },
    "SPIRAM_OCT": {
        "name": "Octal-SPIRAM（八线外部内存）",
        "summary": "让 ESP32-S3 按 Octal（八线）模式连接 PSRAM，适用于明确配备 Octal PSRAM 的 S3 模组。",
        "warning": "Quad 与 Octal 是硬件接线/工作模式差异，选错可能导致启动失败、找不到 PSRAM 或运行不稳定。",
        "beginner_choice": "仅在模组资料明确标注 Octal PSRAM 时选择；不确定就用标准版。",
    },
    "OTA": {
        "name": "OTA（无线固件升级分区）",
        "summary": "使用两个应用分区保存当前和待升级固件，让设备能把新固件写到备用分区后切换启动。",
        "warning": "这里只是编译 OTA 分区布局，不会自动提供下载服务器、升级程序、签名校验或一键推送。首次仍需通过 USB/串口刷入完整固件。",
        "beginner_choice": "只是烧录后长期运行同一版本时选标准版；确定要自行开发无线升级流程时再选 OTA。",
    },
    "D2WD": {
        "name": "ESP32-D2WD 专用版",
        "summary": "针对内部集成 2MB Flash 的 ESP32-D2WD 芯片调整编译配置。",
        "warning": "这不是普通 ESP32-WROOM 的容量选项，只有芯片型号确实是 ESP32-D2WD 才能选择。",
        "beginner_choice": "不确定芯片完整型号时使用标准版。",
    },
    "UNICORE": {
        "name": "单核版（UNICORE）",
        "summary": "把 ESP32 配置为只使用一个 CPU 核心，适合少数单核硬件或特殊兼容场景。",
        "warning": "普通双核 ESP32 通常不需要，选择后不会让程序更快。",
        "beginner_choice": "没有明确的单核需求时使用标准版。",
    },
}


def get_micropython_dir() -> Path:
    configured = os.getenv("MICROPYTHON_DIR") or Config().get_jsonpath(
        "$.ProjectConfig.micropython_dir"
    )
    return Path(configured or "/data/micropython/micropython").resolve()


def _read_board(board_dir: Path) -> Optional[dict]:
    metadata_path = board_dir / "board.json"
    if not metadata_path.is_file():
        return None
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None

    device_type = MCU_TO_DEVICE.get(str(metadata.get("mcu", "")).lower())
    if not device_type:
        return None

    variants = []
    for value, label in (metadata.get("variants") or {}).items():
        # IDF3 是历史兼容项，当前部署使用 ESP-IDF 5，不向用户提供。
        if value == "IDF3":
            continue
        variants.append(
            {
                "value": value,
                "label": label,
                "guidance": VARIANT_GUIDANCE.get(
                    value,
                    {
                        "name": label,
                        "summary": "这是当前 MicroPython 开发板源码提供的专用编译变体。",
                        "warning": "变体通常对应特定硬件或分区配置，选择前请核对开发板说明。",
                        "beginner_choice": "不确定时使用标准版。",
                    },
                ),
            }
        )

    return {
        "value": board_dir.name,
        "label": metadata.get("product") or board_dir.name,
        "vendor": metadata.get("vendor") or "",
        "device_type": device_type,
        "variants": variants,
        "features": metadata.get("features") or [],
    }


def discover_build_options(micropython_dir: Optional[Path] = None) -> dict:
    """只返回当前 MicroPython 源码树真实存在的目标，避免页面给出假选项。"""
    root = Path(micropython_dir or get_micropython_dir())
    boards: List[dict] = []
    for port in ("esp8266", "esp32"):
        boards_dir = root / "ports" / port / "boards"
        if not boards_dir.is_dir():
            continue
        for board_dir in sorted(boards_dir.iterdir()):
            if not board_dir.is_dir() or board_dir.name.startswith("WEB_"):
                continue
            board = _read_board(board_dir)
            if board:
                if board["value"] in PLATFORM_OTA_BOARDS and not any(
                    variant["value"] == "OTA" for variant in board["variants"]
                ):
                    guidance = dict(VARIANT_GUIDANCE["OTA"])
                    guidance["warning"] += (
                        " C3 平台扩展固定使用 4MiB Flash 布局，"
                        "芯片模组必须至少有 4MiB Flash。"
                    )
                    board["variants"].append(
                        {
                            "value": "OTA",
                            "label": "OTA（平台扩展，已验证）",
                            "platform_extension": True,
                            "guidance": guidance,
                        }
                    )
                boards.append(board)

    grouped: Dict[str, List[dict]] = {}
    for board in boards:
        if board["device_type"] == "ESP8266":
            # ESP8266 的 FLASH_512K/FLASH_1M 已由 Flash 下拉框统一控制。
            board["variants"] = []
        grouped.setdefault(board["device_type"], []).append(board)

    devices = []
    for device_type in DEVICE_LABELS:
        device_boards = grouped.get(device_type, [])
        if not device_boards:
            continue
        default_board = DEFAULT_BOARDS.get(device_type)
        device_boards.sort(key=lambda item: (item["value"] != default_board, item["label"]))
        devices.append(
            {
                "value": device_type,
                "label": DEVICE_LABELS[device_type],
                "default_board": default_board if any(
                    item["value"] == default_board for item in device_boards
                ) else device_boards[0]["value"],
                "default_flash_size": "2MB" if device_type == "ESP8266" else "AUTO",
                "flash_sizes": (
                    ESP8266_FLASH_SIZES if device_type == "ESP8266" else ESP_FLASH_SIZES
                ),
                "boards": device_boards,
            }
        )

    return {"devices": devices}


def normalize_device_type(device_type: str) -> str:
    aliases = {
        "ESP32_S": "ESP32",
        "ESP32 S": "ESP32",
        "ESP32 S2": "ESP32_S2",
        "ESP32 S3": "ESP32_S3",
        "ESP32 C3": "ESP32_C3",
    }
    return aliases.get(device_type, device_type)


def normalize_flash_size(flash_size: str) -> str:
    normalized = FLASH_ALIASES.get(str(flash_size).strip().upper())
    if not normalized:
        raise ValueError(f"不支持的 Flash 大小：{flash_size}")
    return normalized


@dataclass
class BuildSelection:
    device_type: str
    flash_size: str
    board: str
    board_variant: str
    effective_board: str
    effective_variant: str

    @property
    def make_arguments(self) -> List[str]:
        result = [f"BOARD={self.effective_board}"]
        if self.effective_variant:
            result.append(f"BOARD_VARIANT={self.effective_variant}")
        return result


def validate_selection(
    device_type: str,
    flash_size: str,
    board: str = "",
    board_variant: str = "",
    micropython_dir: Optional[Path] = None,
    prepare_board: bool = False,
) -> BuildSelection:
    root = Path(micropython_dir or get_micropython_dir())
    device_type = normalize_device_type(device_type)
    flash_size = normalize_flash_size(flash_size)
    options = discover_build_options(root)
    device = next(
        (item for item in options["devices"] if item["value"] == device_type), None
    )
    if not device:
        raise ValueError(f"当前编译环境不支持设备：{device_type}")

    board = board or device["default_board"]
    board_option = next(
        (item for item in device["boards"] if item["value"] == board), None
    )
    if not board_option:
        raise ValueError(f"开发板 {board} 不属于 {device_type} 或当前源码中不存在")

    if flash_size not in device["flash_sizes"]:
        raise ValueError(f"{device_type} 不支持 Flash 选项 {flash_size}")

    board_variant = "" if board_variant in ("", "STANDARD", "DEFAULT") else board_variant
    allowed_variants = {item["value"] for item in board_option["variants"]}
    if board_variant and board_variant not in allowed_variants:
        raise ValueError(f"开发板 {board} 不支持变体 {board_variant}")

    if device_type == "ESP8266":
        effective_variant = ESP8266_FLASH_VARIANTS[flash_size]
        effective_board = board
    else:
        if board_variant and flash_size != "AUTO":
            raise ValueError("选择开发板变体时请把 Flash 大小设为“自动/开发板默认”")
        if board_variant == "OTA":
            # 所有 OTA 构建都使用独立 WEB_* 板目录，并显式启用 ESP-IDF
            # bootloader 回滚。上游已有 OTA variant 的板继续使用
            # sdkconfig.ota；平台生成的 sdkconfig.web 作为最后覆盖层。
            platform_extension = board in PLATFORM_OTA_BOARDS
            effective_variant = "" if platform_extension else "OTA"
            effective_board = (
                _prepare_ota_board(root, board, platform_extension)
                if prepare_board
                else board
            )
        else:
            effective_variant = board_variant
            effective_board = board
        if not board_variant and flash_size != "AUTO" and prepare_board:
            effective_board = _prepare_flash_board(root, board, flash_size)

    return BuildSelection(
        device_type=device_type,
        flash_size=flash_size,
        board=board,
        board_variant=board_variant,
        effective_board=effective_board,
        effective_variant=effective_variant,
    )


def _prepare_flash_board(root: Path, board: str, flash_size: str) -> str:
    """为显式 Flash 容量生成板级覆写，使页面参数真正进入 sdkconfig。"""
    source = root / "ports" / "esp32" / "boards" / board
    if not source.is_dir():
        raise ValueError(f"找不到开发板目录：{source}")

    safe_board = re.sub(r"[^A-Z0-9_]", "_", board.upper())
    effective_board = f"WEB_{safe_board}_{flash_size.replace('MB', 'M')}"
    destination = source.parent / effective_board
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)

    size_number = flash_size.removesuffix("MB")
    overrides = ["# Web 编译平台：显式 Flash 容量覆写"]
    for candidate in ("2", "4", "8", "16"):
        value = "y" if candidate == size_number else ""
        overrides.append(f"CONFIG_ESPTOOLPY_FLASHSIZE_{candidate}MB={value}")
    overrides.extend(
        [
            f'CONFIG_ESPTOOLPY_FLASHSIZE="{flash_size}"',
            "CONFIG_PARTITION_TABLE_CUSTOM=y",
            f'CONFIG_PARTITION_TABLE_CUSTOM_FILENAME="partitions-{size_number}MiB.csv"',
            f'CONFIG_PARTITION_TABLE_FILENAME="partitions-{size_number}MiB.csv"',
        ]
    )
    _write_web_sdkconfig(destination, overrides)
    return effective_board


def _prepare_ota_board(root: Path, board: str, platform_extension: bool) -> str:
    """生成隔离的 OTA 板配置，并启用新固件确认/自动回滚能力。"""
    source = root / "ports" / "esp32" / "boards" / board
    if not source.is_dir():
        raise ValueError(f"找不到开发板目录：{source}")

    safe_board = re.sub(r"[^A-Z0-9_]", "_", board.upper())
    effective_board = f"WEB_{safe_board}_OTA"
    destination = source.parent / effective_board
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)

    overrides = [
        "# Web 编译平台：启用 OTA 新固件确认与自动回滚",
        "CONFIG_BOOTLOADER_APP_ROLLBACK_ENABLE=y",
    ]
    if platform_extension:
        partition_path = root / "ports" / "esp32" / C3_OTA_PARTITION_FILE
        partition_path.write_text(C3_OTA_PARTITIONS, encoding="utf-8")
        overrides.extend(
            [
                "# Web 编译平台：ESP32-C3 4MiB OTA 双应用分区",
                "CONFIG_ESPTOOLPY_FLASHSIZE_4MB=y",
                'CONFIG_ESPTOOLPY_FLASHSIZE="4MB"',
                "CONFIG_PARTITION_TABLE_CUSTOM=y",
                f'CONFIG_PARTITION_TABLE_CUSTOM_FILENAME="{C3_OTA_PARTITION_FILE}"',
                f'CONFIG_PARTITION_TABLE_FILENAME="{C3_OTA_PARTITION_FILE}"',
                "CONFIG_COMPILER_OPTIMIZATION_SIZE=y",
                "CONFIG_COMPILER_OPTIMIZATION_PERF=n",
                "CONFIG_COMPILER_OPTIMIZATION_CHECKS_SILENT=y",
            ]
        )
    _write_web_sdkconfig(destination, overrides)
    return effective_board


def _write_web_sdkconfig(destination: Path, overrides: List[str]) -> None:
    """写独立覆盖层，并让复制后的板级 CMake 明确在最后加载它。

    不能只新增 sdkconfig.board：部分上游板（例如 ESP32_GENERIC_C3）的
    mpconfigboard.cmake 并不会自动引用这个文件。显式追加到
    SDKCONFIG_DEFAULTS 才能保证页面参数进入最终 sdkconfig。
    """
    sdkconfig_path = destination / "sdkconfig.web"
    sdkconfig_path.write_text("\n".join(overrides) + "\n", encoding="utf-8")

    cmake_path = destination / "mpconfigboard.cmake"
    if not cmake_path.is_file():
        raise ValueError(f"找不到开发板 CMake 配置：{cmake_path}")
    cmake = cmake_path.read_text(encoding="utf-8").rstrip()
    cmake += (
        "\n\n# Web 编译平台：最后加载页面选择产生的配置覆盖层\n"
        "set(SDKCONFIG_DEFAULTS\n"
        "    ${SDKCONFIG_DEFAULTS}\n"
        "    ${MICROPY_BOARD_DIR}/sdkconfig.web\n"
        ")\n"
    )
    cmake_path.write_text(cmake, encoding="utf-8")
