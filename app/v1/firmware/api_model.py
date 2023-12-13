# !/usr/bin/env python
# -*- coding:utf-8 -*-
# project name: compile-mpy-firmware
# author: "Lei Yong" 
# creation time: 2023-11-28 20:04
# Email: leiyong711@163.com

from datetime import datetime
from utils.log import lg
from typing import Optional,List, Any, Dict
from pydantic import EmailStr, Field, ValidationError, validator
from pydantic import BaseModel, typing
from utils.exception_handling import SucceedOut, UnicornException
from pydantic_sqlalchemy import sqlalchemy_to_pydantic
from app.v1.firmware.db_model import Firmware, FirmwareWaitCompiled


class CreateCompilationTaskData(BaseModel):
    id: int = Field(..., title="任务id")
    msg: str = Field(None, title="提示")


class CreateCompilationTaskOUT(SucceedOut):
    """创建编译任务"""
    data: CreateCompilationTaskData = Field(..., title="结果")


FirmwareModelPydantic = sqlalchemy_to_pydantic(
    Firmware,
    exclude=[
        'firmware_file_path',               # 固件文件路径
        'custom_source_code_file_path',     # 自定义源码文件路径
    ]
)


class ExtendedPydanticModel(FirmwareModelPydantic):
    """扩展固件模型"""
    retrieve_password: bool

    # @validator('retrieve_password', pre=True)
    # def set_retrieve_password(cls, v, values):
    #     lg.debug(f"v: {v}\tvalues: {values}")
    #     if 'retrieve_password' in values:
    #         return bool(values['retrieve_password'])
    #     return False
    @validator('retrieve_password', pre=True)
    def set_retrieve_password(cls, v):
        return bool(v)


class FirmwareListData(BaseModel):
    """固件列表数据"""
    total: int
    items: List[ExtendedPydanticModel]


class GetFirmwareListOut(SucceedOut):
    """获取固件列表"""
    data: FirmwareListData = Field(..., title="固件列表")

    class Config:
        json_encoders = {
            datetime: lambda v: v.strftime('%Y-%m-%d %H:%M:%S') if v else None
        }


FirmwareWaitCompiledModelPydantic = sqlalchemy_to_pydantic(
    FirmwareWaitCompiled,
    exclude=[
        "retrieve_password",
        "custom_source_code_file_path"
    ]
)


class FirmwareWaitCompiledExtendedPydanticModel(FirmwareWaitCompiledModelPydantic):
    """扩展固件模型"""
    retrieve_password: bool

    @validator('retrieve_password', pre=True)
    def set_retrieve_password(cls, v):
        return bool(v)
    # status: str
    #
    # @validator('status', pre=True)
    # def set_retrieve_password(cls, v):
    #     lg.debug(v)
    #     # 0:编译成功,1:编译失败,2:编译中,3:等待编译
    #     return "编译中" if v == 0 else "编译失败" if v == 1 else "编译中" if v == 2 else "等待编译"


class FirmwareWaitCompiledListData(BaseModel):
    """待编译固件列表数据"""
    # PydanticUser = sqlalchemy_to_pydantic(
    #     FirmwareWaitCompiled,
    #     exclude=[
    #         "retrieve_password",
    #         "custom_source_code_file_path"
    #     ]
    # )
    total: int
    items: List[FirmwareWaitCompiledExtendedPydanticModel]


class GetFirmwareWaitCompiledListOut(SucceedOut):
    """获取待编译固件列表"""
    data: FirmwareWaitCompiledListData = Field(..., title="待编译固件列表")

    class Config:
        json_encoders = {
            datetime: lambda v: v.strftime('%Y-%m-%d %H:%M:%S') if v else None
        }