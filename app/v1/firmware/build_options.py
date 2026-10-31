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
        variants.append({"value": value, "label": label})

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
        effective_variant = board_variant
        effective_board = board
        if flash_size != "AUTO" and prepare_board:
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

    sdkconfig_path = destination / "sdkconfig.board"
    previous = sdkconfig_path.read_text(encoding="utf-8") if sdkconfig_path.exists() else ""
    size_number = flash_size.removesuffix("MB")
    overrides = ["", "# Web 编译平台：显式 Flash 容量覆写"]
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
    sdkconfig_path.write_text(previous.rstrip() + "\n" + "\n".join(overrides) + "\n", encoding="utf-8")
    return effective_board
