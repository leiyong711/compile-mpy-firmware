# Docker 一键部署教程

## 镜像说明

Docker Hub 仓库：`leiyong711/compile-mpy-firmware`

| 标签 | 用途 |
| --- | --- |
| `latest` | 当前稳定版，ARM64 |
| `latest-arm64` | 明确指定 ARM64 架构 |
| `v2.0.0-arm64` | 本次功能版本，固定标签 |
| `toolchain-mpy1.22.2-idf5.0.4-arm64` | 工具链基础镜像，供主镜像构建使用 |

镜像包含 MicroPython v1.22.2、ESP-IDF v5.0.4、ESP32/S2/S3/C3 交叉工具链，以及 ESP8266 ARM64 SDK/sysroot。当前发布只支持 `linux/arm64`。

ESP8266 使用 Debian ARM64 可用的较新 GCC，编译环境会设置 `CFLAGS_EXTRA=-Wno-error` 来兼容上游旧版 lwIP 头文件中的历史警告，并把工具链内的 `esptool.py` 加入 PATH；这与实机原生环境的设置一致，不会忽略真正的编译错误。

## 方法一：Docker Compose（推荐）

新建目录和 `docker-compose.yml`：

```yaml
services:
  compile-mpy-firmware:
    image: leiyong711/compile-mpy-firmware:latest
    platform: linux/arm64
    container_name: compile-mpy-firmware
    restart: unless-stopped
    ports:
      - "9001:9000"
    environment:
      TZ: Asia/Shanghai
      BUILD_JOBS: "4"
    volumes:
      - ./data:/data/compile-mpy-runtime
```

启动：

```bash
docker compose pull
docker compose up -d
docker compose ps
```

浏览器打开 `http://树莓派IP:9001/`。

## 方法二：单条 docker run 命令

```bash
mkdir -p /data/compile-mpy-runtime
docker run -d \
  --name compile-mpy-firmware \
  --restart unless-stopped \
  -p 9001:9000 \
  -e TZ=Asia/Shanghai \
  -e BUILD_JOBS=4 \
  -v /data/compile-mpy-runtime:/data/compile-mpy-runtime \
  leiyong711/compile-mpy-firmware:latest
```

## 健康检查和验证

```bash
docker ps --filter name=compile-mpy-firmware
docker inspect --format '{{json .State.Health}}' compile-mpy-firmware
curl -fsS http://127.0.0.1:9001/api/build-options
docker logs --tail=100 compile-mpy-firmware
```

`/api/build-options` 应返回 `devices` 数组。数组内容来自镜像中实际 MicroPython 源码，而不是写死在前端。

WebSocket 验证地址格式：

```text
ws://树莓派IP:9001/api/ws/progress/任务ID
```

## 从源码构建应用镜像

普通用户直接拉取已发布镜像即可。维护者需要先有工具链基础镜像：

```bash
git clone -b leo https://github.com/leiyong711/compile-mpy-firmware.git
cd compile-mpy-firmware
docker build \
  -t leiyong711/compile-mpy-firmware:v2.0.0-arm64 \
  -t leiyong711/compile-mpy-firmware:latest-arm64 \
  -t leiyong711/compile-mpy-firmware:latest .
```

发布：

```bash
docker push leiyong711/compile-mpy-firmware:v2.0.0-arm64
docker push leiyong711/compile-mpy-firmware:latest-arm64
docker push leiyong711/compile-mpy-firmware:latest
```

## 数据和升级策略

容器内 `/data/compile-mpy-runtime` 必须挂载到宿主机。这里保存：

- `firmware.db`：任务、进度和固件记录；
- `logs/`：应用日志；
- `res_pack/upload/`：上传源文件；
- `res_pack/after_compilation/`：生成的固件与源码包。

升级镜像不会覆盖这些文件：

```bash
docker compose pull
docker compose up -d
```

## 资源调优

- 树莓派 5/8GB：`BUILD_JOBS=4`；
- 树莓派 4/4GB：建议 `BUILD_JOBS=2` 或 `4`；
- 2GB 内存设备：建议 `BUILD_JOBS=2` 并启用交换空间；
- 同一服务按队列串行编译，避免多个大编译任务抢占内存。

## 安全提示

此版本面向可信局域网，没有登录鉴权。不要直接映射到公网。若必须远程访问，请在前面增加带身份验证和 HTTPS 的反向代理，并限制上传大小、访问来源和速率。

工具链镜像包含来自 MicroPython、Espressif ESP-IDF/ESP8266 NONOS SDK 和 GNU 工具链的文件；二次分发时应继续保留各上游项目许可证与源码来源说明。
