ARG TOOLCHAIN_IMAGE=leiyong711/compile-mpy-firmware:toolchain-mpy1.22.2-idf5.0.4-arm64
FROM ${TOOLCHAIN_IMAGE}

ENV COMPILE_MPY_DATA_DIR=/data/compile-mpy-runtime \
    MICROPYTHON_DIR=/opt/micropython \
    ESP_IDF_EXPORT=/opt/esp-idf-v5.0.4/export.sh \
    ESP8266_SDK_ROOT=/opt/esp-open-sdk/xtensa-lx106-elf \
    BUILD_JOBS=4 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN python3 -m venv /opt/compile-mpy-venv \
    && /opt/compile-mpy-venv/bin/pip install --upgrade "pip<25" "setuptools==65.5.1" wheel \
    && /opt/compile-mpy-venv/bin/pip install -r /app/requirements.txt

COPY . /app
RUN chmod +x /app/docker/entrypoint.sh \
    && mkdir -p /data/compile-mpy-runtime/logs

EXPOSE 9000
VOLUME ["/data/compile-mpy-runtime"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:9000/ >/dev/null || exit 1

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["/opt/compile-mpy-venv/bin/python", "-m", "gunicorn.app.wsgiapp", "main:app", "--workers", "1", "--worker-class", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:9000", "--access-logfile", "-", "--error-logfile", "-"]

