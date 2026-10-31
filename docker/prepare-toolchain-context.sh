#!/bin/bash
set -euo pipefail

project_dir="$(cd "$(dirname "$0")/.." && pwd)"
context_dir="${project_dir}/docker/toolchain-context"

if [ "$(id -u)" -ne 0 ]; then
    echo "请使用 root 执行此脚本。" >&2
    exit 1
fi

rm -rf "${context_dir}"
mkdir -p "${context_dir}"
rsync -a --exclude='.git' --exclude='build-*' /opt/esp-idf-v5.0.4/ "${context_dir}/esp-idf-v5.0.4/"
rsync -a --exclude='__pycache__' /root/.espressif/ "${context_dir}/espressif/"
rsync -a /opt/esp-open-sdk/ "${context_dir}/esp-open-sdk/"
rsync -a --exclude='.git' --exclude='build-*' /data/micropython/micropython/ "${context_dir}/micropython/"

echo "工具链上下文已生成：${context_dir}"
