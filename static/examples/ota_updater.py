"""ESP32 / ESP32-C3 MicroPython OTA 更新器。

适用前提：
1. 设备已经通过串口刷入本平台生成的 OTA 版 firmware.bin；
2. URL 指向固件包中的 ota-application.bin，而不是 firmware.bin；
3. expected_sha256 必须从可信渠道写入设备，不能和固件一起从不可信 HTTP 获取。

本模块按 4096 字节流式下载并写入“当前未运行”的 OTA 分区，不会把整个
固件读进 RAM。只有长度和 SHA-256 都校验成功后才切换启动分区。
"""

try:
    import usocket as socket
except ImportError:
    import socket

try:
    import ussl as ssl
except ImportError:
    import ssl

try:
    import uhashlib as hashlib
except ImportError:
    import hashlib

try:
    import ubinascii as binascii
except ImportError:
    import binascii

import gc
import machine
import os
import time
from esp32 import Partition


BLOCK_SIZE = 4096
PENDING_FILE = "/ota_pending.txt"


class OTAError(Exception):
    """OTA 下载、校验或写入失败。发生异常时不会切换启动分区。"""


def _parse_url(url):
    """把 http(s)://主机[:端口]/路径 拆分成连接参数。"""
    if url.startswith("https://"):
        scheme, default_port, secure = "https", 443, True
        rest = url[8:]
    elif url.startswith("http://"):
        scheme, default_port, secure = "http", 80, False
        rest = url[7:]
    else:
        raise OTAError("URL 必须以 http:// 或 https:// 开头")

    if "/" in rest:
        authority, path_tail = rest.split("/", 1)
        path = "/" + path_tail
    else:
        authority, path = rest, "/"
    if not authority or "@" in authority:
        raise OTAError("URL 主机名为空，或包含不允许的用户名密码")
    if authority.startswith("["):
        raise OTAError("示例更新器暂不处理 IPv6 字面地址，请使用域名或 IPv4")

    if ":" in authority:
        host, port_text = authority.rsplit(":", 1)
        try:
            port = int(port_text)
        except ValueError:
            raise OTAError("URL 端口不是数字")
    else:
        host, port = authority, default_port

    host_header = host if port == default_port else "%s:%d" % (host, port)
    return scheme, host, port, path, host_header, secure


def _socket_write_all(sock, data):
    """兼容普通 socket 与 SSL socket，确保请求全部发送。"""
    offset = 0
    while offset < len(data):
        if hasattr(sock, "write"):
            written = sock.write(data[offset:])
        else:
            written = sock.send(data[offset:])
        if not written:
            raise OTAError("发送 HTTP 请求失败")
        offset += written


def _open_http_stream(url):
    """打开 HTTP 响应，返回 socket、文件流和 Content-Length。"""
    _scheme, host, port, path, host_header, secure = _parse_url(url)
    address = socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)[0][-1]
    sock = socket.socket()
    sock.settimeout(20)
    try:
        sock.connect(address)
        if secure:
            # 部分 MicroPython 固件没有 CA 证书仓库，因此 HTTPS 不一定自动验证
            # 服务器身份。expected_sha256 仍必须来自可信渠道；正式产品建议再做
            # 证书固定或数字签名验证。
            try:
                sock = ssl.wrap_socket(sock, server_hostname=host)
            except TypeError:
                sock = ssl.wrap_socket(sock)

        request = (
            "GET %s HTTP/1.1\r\n"
            "Host: %s\r\n"
            "User-Agent: MicroPython-OTA/1.0\r\n"
            "Accept: application/octet-stream\r\n"
            "Accept-Encoding: identity\r\n"
            "Connection: close\r\n\r\n"
        ) % (path, host_header)
        _socket_write_all(sock, request.encode())
        stream = sock.makefile("rb", 0)

        status_line = stream.readline()
        if not status_line:
            raise OTAError("服务器没有返回 HTTP 状态行")
        parts = status_line.decode("latin-1").strip().split(" ", 2)
        if len(parts) < 2 or parts[1] != "200":
            raise OTAError("下载失败，HTTP 状态：%s" % status_line.decode().strip())

        headers = {}
        while True:
            line = stream.readline()
            if line in (b"", b"\r\n", b"\n"):
                break
            name, value = line.decode("latin-1").split(":", 1)
            headers[name.strip().lower()] = value.strip()

        if headers.get("transfer-encoding", "").lower() == "chunked":
            raise OTAError("服务器使用 chunked 传输；请配置为返回 Content-Length")
        if "content-length" not in headers:
            raise OTAError("服务器没有返回 Content-Length，无法安全校验长度")
        return sock, stream, int(headers["content-length"])
    except Exception:
        try:
            sock.close()
        except Exception:
            pass
        raise


def _read_exact(stream, size):
    """网络一次可能读不满 size；循环读取直到够长或确认断线。"""
    data = bytearray()
    while len(data) < size:
        part = stream.read(size - len(data))
        if not part:
            raise OTAError("固件下载提前结束：需要 %d 字节，只收到 %d 字节" % (size, len(data)))
        data.extend(part)
    return data


def _default_progress(written, total):
    percent = written * 100 // total
    print("OTA：%d/%d 字节，%d%%" % (written, total, percent))


def install(url, expected_sha256, expected_size=None, progress=None, reboot=True):
    """下载、校验并安装 OTA 应用镜像。

    参数：
    - url：ota-application.bin 的直接下载地址；
    - expected_sha256：可信的 64 位十六进制 SHA-256；
    - expected_size：可信的文件字节数；传 None 时只使用 HTTP 长度；
    - progress：可选回调 progress(已写字节, 总字节)；
    - reboot：成功后是否立即硬重启，默认 True。
    """
    expected_sha256 = expected_sha256.strip().lower()
    if len(expected_sha256) != 64 or any(c not in "0123456789abcdef" for c in expected_sha256):
        raise OTAError("expected_sha256 必须是 64 位十六进制字符串")
    if progress is None:
        progress = _default_progress

    running = Partition(Partition.RUNNING)
    target = running.get_next_update()
    target_size = target.info()[3]
    print("当前分区：", running.info()[4], "目标分区：", target.info()[4])

    sock = stream = None
    try:
        sock, stream, content_length = _open_http_stream(url)
        if expected_size is not None and int(expected_size) != content_length:
            raise OTAError(
                "服务器文件长度 %d 与可信长度 %d 不一致"
                % (content_length, int(expected_size))
            )
        if content_length <= 0 or content_length > target_size:
            raise OTAError(
                "应用镜像 %d 字节，无法放入目标分区 %d 字节"
                % (content_length, target_size)
            )

        digest = hashlib.sha256()
        remaining = content_length
        block_number = 0
        written = 0
        while remaining:
            actual_size = min(BLOCK_SIZE, remaining)
            data = _read_exact(stream, actual_size)
            if block_number == 0 and data[0] != 0xE9:
                raise OTAError("文件不是 ESP32 应用镜像：首字节不是 0xE9")

            digest.update(data)
            if actual_size < BLOCK_SIZE:
                # Flash 擦除/写入以 4096 字节扇区为单位，最后一块用 0xFF 补齐；
                # 哈希只计算真实文件内容，不计算补齐字节。
                padded = bytearray([0xFF]) * BLOCK_SIZE
                padded[:actual_size] = data
                data = padded
            target.writeblocks(block_number, data)

            written += actual_size
            remaining -= actual_size
            block_number += 1
            if block_number == 1 or remaining == 0 or block_number % 16 == 0:
                progress(written, content_length)
            del data
            gc.collect()

        actual_sha256 = binascii.hexlify(digest.digest()).decode().lower()
        if actual_sha256 != expected_sha256:
            raise OTAError(
                "SHA-256 校验失败：期望 %s，实际 %s"
                % (expected_sha256, actual_sha256)
            )

        # 只有完整写入且哈希一致后，才留下待确认标记并切换启动分区。
        # 如果 set_boot() 失败，立即删除标记，避免旧固件误以为自己是等待
        # 确认的新版本。
        with open(PENDING_FILE, "w") as marker:
            marker.write(actual_sha256 + "\n")
        try:
            target.set_boot()
        except Exception:
            try:
                os.remove(PENDING_FILE)
            except OSError:
                pass
            raise
        print("OTA 写入和校验成功，下次将从", target.info()[4], "启动")

        if reboot:
            time.sleep_ms(300)
            machine.reset()  # 必须硬重启，不要用 deepsleep 代替
        return {
            "partition": target.info()[4],
            "size": content_length,
            "sha256": actual_sha256,
        }
    finally:
        if stream is not None:
            try:
                stream.close()
            except Exception:
                pass
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass

