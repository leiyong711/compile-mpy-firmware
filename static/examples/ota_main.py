"""OTA 使用示例。

第一次使用：
1. 修改下面的 Wi-Fi、URL、SHA-256 和文件大小；
2. 把 ota_updater.py、ota_boot.py 和本文件上传到设备；
3. 将本文件改名为 main.py；
4. 先保持 START_UPDATE=False，确认普通业务能启动；
5. 准备升级时改为 True 并重启一次，升级成功后新固件应改回 False。
"""

import network
import socket
import time

from ota_boot import confirm_ota, ota_pending, rollback_to_previous
from ota_updater import install


# ===== 必须按实际环境修改 =====
WIFI_SSID = "请填写WiFi名称"
WIFI_PASSWORD = "请填写WiFi密码"

# 必须直接指向 ota-application.bin。使用本平台接口时可写成：
# http://树莓派IP:9001/api/ota/固件ID/application.bin
FIRMWARE_URL = "http://192.168.0.106:9001/api/ota/4/application.bin"

# 从本平台 OTA manifest 页面复制，不能随便填写。
EXPECTED_SHA256 = "请填写64位SHA256"
EXPECTED_SIZE = 0

# 自检目标应是设备确实依赖的局域网服务，不要照抄一个设备访问不到的公网域名。
SELF_TEST_HOST = "192.168.0.106"
SELF_TEST_PORT = 9001

# 只有准备执行升级的那一次才改成 True；新固件中应恢复为 False。
START_UPDATE = False


def connect_wifi(timeout_seconds=20):
    """连接 Wi-Fi，超时就抛异常，不让坏网络状态被误判为自检成功。"""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        deadline = time.time() + timeout_seconds
        while not wlan.isconnected() and time.time() < deadline:
            time.sleep_ms(250)
    if not wlan.isconnected():
        raise RuntimeError("Wi-Fi 连接超时")
    print("Wi-Fi 已连接：", wlan.ifconfig()[0])
    return wlan


def business_self_test():
    """示例核心自检；实际项目应再检查传感器、文件和业务服务。"""
    # 验证网络栈能解析/访问升级服务器的地址。这里不会真正下载固件。
    socket.getaddrinfo(SELF_TEST_HOST, SELF_TEST_PORT)
    # 可以在这里加入：读取关键配置、初始化传感器、检查数据库等。
    return True


def main():
    connect_wifi()

    # OTA 后第一次启动，先做业务自检。成功才确认；失败则主动回旧固件。
    if ota_pending():
        try:
            if not business_self_test():
                raise RuntimeError("业务自检返回失败")
            confirm_ota()
        except Exception as error:
            print("新固件自检失败：", error)
            rollback_to_previous()

    if START_UPDATE:
        if EXPECTED_SIZE <= 0:
            raise ValueError("请先填写 manifest 中的 EXPECTED_SIZE")
        install(
            FIRMWARE_URL,
            EXPECTED_SHA256,
            expected_size=EXPECTED_SIZE,
            reboot=True,
        )

    print("正常业务程序从这里继续运行")


main()
