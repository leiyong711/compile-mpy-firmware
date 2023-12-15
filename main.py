# !/usr/bin/env python
# -*- coding:utf-8 -*-
# project name: compile-mpy-firmware
# author: "Lei Yong" 
# creation time: 2023-11-28 19:55
# Email: leiyong711@163.com

import json

# 不要移动位置，主要为了保证初始化时的配置文件的位置
from utils.config import Config
config = Config(custom_config=False)

import os
import io
import re
import time
import logging
import uvicorn
import asyncio
import threading
from starlette.requests import Request
from app import create_app
from utils.log import lg
from urllib.parse import urlparse
from utils.tools import get_session
from utils.exception_handling import *
from fastapi.responses import JSONResponse
from fastapi.responses import StreamingResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

_session = get_session()

# 屏蔽定时任务INFO级日志
logging.basicConfig()
logging.getLogger('apscheduler').setLevel(logging.ERROR)
logging.getLevelName(os.environ.get("LOG_LEVEL", "ERROR"))
# 屏蔽fastapi INFO级日志
logging.getLogger('fastapi').setLevel(logging.ERROR)
logging.getLevelName(os.environ.get("LOG_LEVEL", "ERROR"))
# 屏蔽uvicorn INFO级日志
logging.getLogger('uvicorn').setLevel(logging.ERROR)
logging.getLevelName(os.environ.get("LOG_LEVEL", "ERROR"))

app = create_app()

# 创建一个templates（模板）对象，以后可以重用。
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.exception_handler(UnicornException)
@app.exception_handler(AssertionEcception)
@app.exception_handler(StarletteHTTPException)
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    # 自定义异常
    if isinstance(exc, UnicornException) or isinstance(exc, AssertionEcception):
        return JSONResponse({"code": exc.code, "status": exc.status, "message": exc.message})

    # HTTP错误
    if isinstance(exc, StarletteHTTPException):
        # 处理图片请求
        if '/api/user/image/' in str(request.url):
            urlPath = urlparse(str(request.url))
            resp = _session.get(f'http://www.pianyilo.com/{urlPath.path}'.replace('/api/user/image', ""))
            return StreamingResponse(io.BytesIO(resp.content), media_type="image/png")

        headers = request.headers["User-Agent"]     # 获取请求头
        data = exc.detail                           # 获取错误信息

        # 判断是否为浏览器请求
        if any(keyword in headers for keyword in ["Mozilla", "Chrome", "Safari"]):
            # 获取请求路径

            # lg.debug(f"\nurl:{request.url}\nbase_url:{request.base_url}\npath: {urlparse(str(request.url)).path}")
            path = urlparse(str(request.url)).path  # 获取请求路径
            lg.debug(f"请求路径：{path}")
            if '/favicon.ico' in path:
                return JSONResponse({})
            elif '/logs' in path:
                wss_url = "ws://127.0.0.1:65000"
                return templates.TemplateResponse("index.html", {"request": request, "webSocketURL": wss_url, "url_host": wss_url.replace("wss",'https').replace('ws','http')})
            elif '/firmwareWaitCompiled' in path:
                return templates.TemplateResponse("firmwareWaitCompiled.html", {"request": request})
            elif '/firmware' in path:
                return templates.TemplateResponse("firmware.html", {"request": request})
            elif '/upload' in path:
                return templates.TemplateResponse("upload.html", {"request": request})
            elif '/' == path:
                return templates.TemplateResponse("firmware.html", {"request": request})

            return templates.TemplateResponse("404.html", {"request": request, "id": id})

        # 返回错误信息
        return JSONResponse({"code": 5000, "status": False, "message": str(data)})

    # 参数验证错误
    elif isinstance(exc, RequestValidationError):
        data = exc.errors()[0]["msg"]
        lg.error(f"{str(request.url).replace(str(request.base_url),'/')}  {str(exc.errors()[0]['loc'])} {str(data)}param=>{str(exc.body)}")
        return JSONResponse({"code": 5000, "status": False, "message": f"{str(exc.errors()[0]['loc'])} {str(data)}"})
    # 未知错误
    else:
        data = "内部异常"
        lg.error(f"{str(request.url).replace(str(request.base_url), '/')}  {data}")
        return JSONResponse({"code": 5000, "status": False, "message": data})


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    inner_ip = re.compile('(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)')
    question = inner_ip.sub(request.client.host, str(request.url))
    if not request.headers.get("X-Real-IP"):
        lg.info(f'用户IP: {request.headers.get("host")}\t路径: {question}\t{round(process_time,4)} s')
    else:
        lg.info(f'用户IP地址: {request.headers.get("X-Real-IP")}\t路径: {question}\t{round(process_time,4)} s')
    # lg.warning(f'路径：{request.url}\t{round(process_time,4)} s')
    return response



if __name__ == "__main__":
    uvicorn.run(
        app,
        host=config.get_jsonpath('$.ProjectConfig.host', '127.0.0.1'),
        port=config.get_jsonpath('$.ProjectConfig.port', 80),
        log_level=config.get_jsonpath('$.ProjectConfig.log_level', 'error'),
        # ssl_keyfile='ssl/jxzxgl.cn.key',
        # ssl_certfile='ssl/jxzxgl.cn.pem'
    )
    'uvicorn main:app --port=9990 --workers=2'
