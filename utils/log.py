# !/usr/bin/env python
# -*- coding:utf-8 -*-
# project name: compile-mpy-firmware
# author: "Lei Yong"
# creation time: 2023-11-28 17:38
# Email: leiyong711@163.com

import time
from loguru import logger as lg
from utils import constants


# logger.remove(handler_id=None)  # 清除之前的设置
# logger.level('ERROR')


# INFO级日志模板初始化配置
lg.add(f"{constants.APP_PATH}/logs/info_log_{time.strftime('%Y_%m_%d')}.log",
       # filter=handler_request,
       level="INFO",
       format='{time:YYYY-MM-DD HH:mm:ss.SSS} - {level} - {file} - {function} - {line} - {message}',
       rotation="00:00",  # 文件过大就会重新生成一个新文件  "12:00"# 每天12点创建新文件
       encoding="utf-8",
       enqueue=True,  # 异步写入
       serialize=False,  # 序列化为json
       retention="10 days",  # 一段时间后会清空
       # compression="zip"  # 保存为zip格式
       )

# ERROR级日志模板初始化配置
lg.add(f"{constants.APP_PATH}/logs/error_log_{time.strftime('%Y_%m_%d')}.log",
       level="ERROR",
       format='{time:YYYY-MM-DD HH:mm:ss.SSS} - {level} - {file} - {function} - {line} - {message}',
       rotation="00:00",  # 文件过大就会重新生成一个新文件  "12:00"# 每天12点创建新文件
       encoding="utf-8",
       enqueue=True,  # 异步写入
       serialize=False,  # 序列化为json
       retention="10 days",  # 一段时间后会清空
       # compression="zip"  # 保存为zip格式
       )

# WARNING级日志模板初始化配置
lg.add(f"{constants.APP_PATH}/logs/warning_log_{time.strftime('%Y_%m_%d')}.log",
       level="WARNING",
       format='{time:YYYY-MM-DD HH:mm:ss.SSS} - {level} - {file} - {function} - {line} - {message}',
       rotation="00:00",  # 文件过大就会重新生成一个新文件  "12:00"# 每天12点创建新文件
       encoding="utf-8",
       enqueue=True,  # 异步写入
       serialize=False,  # 序列化为json
       retention="10 days",  # 一段时间后会清空
       # compression="zip"  # 保存为zip格式
       )

# DEBUG级日志模板初始化配置
lg.add(f"{constants.APP_PATH}/logs/debug_log_{time.strftime('%Y_%m_%d')}.log",
       level="DEBUG",
       format='{time:YYYY-MM-DD HH:mm:ss.SSS} - {level} - {file} - {function} - {line} - {message}',
       rotation="00:00",  # 文件过大就会重新生成一个新文件  "12:00"# 每天12点创建新文件
       encoding="utf-8",
       enqueue=True,  # 异步写入
       serialize=False,  # 序列化为json
       retention="10 days",  # 一段时间后会清空
       # compression="zip"  # 保存为zip格式
       )
