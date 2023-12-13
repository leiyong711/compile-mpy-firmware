# !/usr/bin/env python
# -*- coding:utf-8 -*-
# project name: compile-mpy-firmware
# author: "Lei Yong"
# creation time: 2023-11-28 19:55
# Email: leiyong711@163.com

from pydantic import BaseModel, typing
from typing import Dict, Any


# 未知异常
class UnicornException(Exception):
    def __init__(self, message: str, code: int = 5000, status: bool = False):
        self.code = code
        self.status = status
        self.message = message


# 验证失败
class AssertionEcception(Exception):
    def __init__(self, message: str, code: int = 5007, status: bool = False):
        self.code = code
        self.status = status
        self.message = message


# 成功的响应模板
class SucceedOut(BaseModel):
    code: int = 2000
    status: bool = True
    message: str = "成功"


# 错误的响应模板
class ErrorOUt(BaseModel):
    code: int = 5000
    status: bool = False
    message: str = "失败"
