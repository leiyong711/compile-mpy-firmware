"""OTA 启动确认与手动回滚辅助代码。

把本文件上传到设备根目录，并在 main.py 中完成 Wi-Fi、传感器等核心自检后
调用 confirm_ota()。不要在 boot.py 的第一行就确认，否则新固件即使业务启动
失败，也失去了自动回滚机会。
"""

import machine
import os
from esp32 import Partition


PENDING_FILE = "/ota_pending.txt"


def ota_pending():
    """返回是否是 OTA 后第一次等待确认的启动。"""
    try:
        os.stat(PENDING_FILE)
        return True
    except OSError:
        return False


def confirm_ota():
    """核心自检成功后确认当前新固件，取消 bootloader 自动回滚。"""
    if not ota_pending():
        return False
    Partition.mark_app_valid_cancel_rollback()
    try:
        os.remove(PENDING_FILE)
    except OSError:
        pass
    print("OTA：新固件自检通过，已确认本次升级")
    return True


def rollback_to_previous():
    """业务自检发现严重问题时，主动切回另一个 OTA 分区并硬重启。"""
    current = Partition(Partition.RUNNING)
    previous = current.get_next_update()
    print("OTA：主动从", current.info()[4], "回滚到", previous.info()[4])
    previous.set_boot()
    machine.reset()

