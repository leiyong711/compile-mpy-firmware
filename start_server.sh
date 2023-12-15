#!/bin/bash
# ¼¤»îĞéÄâ»·¾³
source /data/compile-mpy-firmware/venv/bin/activate

gunicorn  main:app -w 1 -k  uvicorn.workers.UvicornWorker -b 0.0.0.0:9000