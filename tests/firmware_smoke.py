"""真实固件编译验证时封入 MicroPython 的最小模块。"""

BUILD_VALIDATION_MARKER = "compile-mpy-firmware-websocket-progress"


def hello():
    return BUILD_VALIDATION_MARKER
