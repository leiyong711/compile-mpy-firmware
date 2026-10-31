#!/bin/sh
set -eu

mkdir -p "${COMPILE_MPY_DATA_DIR}/logs"
mkdir -p "${COMPILE_MPY_DATA_DIR}/res_pack/upload"
mkdir -p "${COMPILE_MPY_DATA_DIR}/res_pack/after_compilation"

exec "$@"

