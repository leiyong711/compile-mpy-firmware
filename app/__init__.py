# !/usr/bin/env python
# -*- coding:utf-8 -*-
# project name: compile-mpy-firmware
# author: "Lei Yong" 
# creation time: 2023-11-28 17:38
# Email: leiyong711@163.com

from utils.log import lg
from fastapi import FastAPI
from utils.config import Config
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.v1.firmware.api import app as firmware_app
from apscheduler.schedulers.asyncio import AsyncIOScheduler

config = Config()


@asynccontextmanager
async def lifespan(app):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(func="job.compilation_tasks:compilation_tasks", id="定时编译固件",
                      args=("定时编译固件",), trigger="interval", seconds=300)
    scheduler.start()
    lg.info("启动调度器...")
    yield
    lg.info("服务已结束")


def create_app():
    app = FastAPI(
        lifespan=lifespan,  # 生命周期
        title=config.get_jsonpath('$.ProjectConfig.project_title', ''),
        version=config.get_jsonpath('$.ProjectConfig.version', ''),
        docs_url=config.get_jsonpath('$.ProjectConfig.api_docs_url', None),
        redoc_url=config.get_jsonpath('$.ProjectConfig.api_redoc_url', None),
        description=config.get_jsonpath('$.ProjectConfig.description', ''),
        # default_response_class=CORJSONResponse
    )

    # 跨域
    app.add_middleware(
        CORSMiddleware,
        allow_origins=['*'],  # 允许跨域请求的域名列表，例如 ['https://example.org', 'https://www.example.org'] 或者 ['*']。
        allow_credentials=True,  # 表示在跨域请求时是否支持cookie，默认为False。
        allow_methods=["*"],  # 允许跨域请求的HTTP方法列表，默认为['GET']，['*'] 表示允许所有HTTP方法。
        allow_headers=["*"],  # 跨域请求支持的HTTP头信息列表。['*'] 表示允许所有头信息。Accept, Accept-Language, Content-Language 和 Content-Type头信息默认全都支持。
        # allow_origin_regex=  # 允许跨域请求的域名正则表达式，例如'https://.*\.example\.org'。
        # expose_headers=  # 表示对浏览器可见的返回结果头信息，默认为[]。
        max_age=600  # 浏览器缓存CORS返回结果的最大时长，默认为600(单位秒)。
    )

    # 路由注册
    app.include_router(firmware_app, prefix="/api")

    return app


