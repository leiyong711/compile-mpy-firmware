# !/usr/bin/env python
# -*- coding:utf-8 -*-
# project name: compile-mpy-firmware
# author: "Lei Yong" 
# creation time: 2023-11-28 20:03
# Email: leiyong711@163.com

import datetime
import traceback
import threading
from utils.log import lg
from utils import constants
from sqlalchemy import Column, Integer, String, Text, DateTime, INTEGER, Float, TIMESTAMP, CHAR, VARCHAR, UniqueConstraint, text, ForeignKey, Table, event, func, extract, Boolean
from dbs.sqlite_connect import Base, SessionLocal, engine


# 已编译固件表的模型类
class Firmware(Base):
    __tablename__ = 'firmware'
    id = Column(Integer, primary_key=True, autoincrement=True, comment='固件ID')                      # 主键，自增
    email = Column(String(255), nullable=False, comment='邮箱')                                       # 邮箱
    device_type = Column(String(255), nullable=False, comment='设备类型')                           # 设备类型
    firmware_file_path = Column(String(255), nullable=False, comment='固件文件路径')                   # 固件文件路径
    custom_source_code_file_path = Column(String(255), nullable=False, comment='自定义源码文件路径')    # 自定义源码文件路径
    flash_size = Column(String(255), nullable=False, comment='Flash大小')                             # Flash大小
    board = Column(String(255), nullable=False, default="", comment='开发板')
    board_variant = Column(String(255), nullable=False, default="", comment='开发板变体')
    compilation_time_consuming = Column(Integer, nullable=False, comment='编译耗时')                   # 编译耗时
    remark = Column(Text, nullable=True, comment='备注')                                              # 备注
    retrieve_password = Column(String(255), nullable=True, comment='提取密码')                         # 提取密码
    upload_time = Column(String(255), nullable=False, comment='上传时间')                              # 上传时间
    start_compilation_time = Column(String(255), nullable=False, comment='开始编译时间')               # 开始编译时间
    create_time = Column(DateTime, default=datetime.datetime.now, comment='创建时间')                  # 创建时间

    def to_dict(self):
        return {c.name: getattr(self, c.name, None) for c in self.__table__.columns}


# 待编译固件表的模型类
class FirmwareWaitCompiled(Base):
    __tablename__ = 'FirmwareWaitCompiled'
    id = Column(Integer, primary_key=True, autoincrement=True, comment='待编译ID')                     # 主键，自增
    email = Column(String(255), nullable=False, comment='邮箱')                                        # 邮箱
    device_type = Column(String(255), nullable=False, comment='设备类型')                           # 设备类型
    custom_source_code_file_path = Column(String(255), nullable=False, comment='自定义源码文件路径')    # 自定义源码文件路径
    flash_size = Column(String(255), nullable=False, comment='Flash大小')                              # Flash大小
    board = Column(String(255), nullable=False, default="", comment='开发板')
    board_variant = Column(String(255), nullable=False, default="", comment='开发板变体')
    retrieve_password = Column(String(255), nullable=True, comment='提取密码')                         # 提取密码
    remark = Column(Text, nullable=True, comment='备注')                                               # 备注
    status = Column(Integer, default=3, nullable=False, comment='编译状态')                            # 编译状态,0:编译成功,1:编译失败,2:编译中,3:等待编译
    err_log = Column(Text, nullable=True, comment='错误日志')                                           # 错误日志
    update_time = Column(String(255), nullable=True, comment='更新时间')                               # 更新时间
    create_time = Column(DateTime, default=datetime.datetime.now, comment='创建时间')                  # 创建时间

    def to_dict(self):
        return {c.name: getattr(self, c.name, None) for c in self.__table__.columns}


class FirmwareBuildProgress(Base):
    """编译进度独立保存，任务完成并从等待表删除后仍可查询。"""

    __tablename__ = "firmware_build_progress"
    task_id = Column(Integer, primary_key=True, comment="编译任务ID")
    percentage = Column(Integer, nullable=False, default=0, comment="进度百分比")
    stage = Column(String(64), nullable=False, default="queued", comment="阶段")
    message = Column(String(512), nullable=False, default="等待编译", comment="进度说明")
    status = Column(String(32), nullable=False, default="queued", comment="任务状态")
    current_step = Column(Integer, nullable=False, default=0, comment="当前编译步骤")
    total_steps = Column(Integer, nullable=False, default=0, comment="总编译步骤")
    updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)

    def to_dict(self):
        return {c.name: getattr(self, c.name, None) for c in self.__table__.columns}

Base.metadata.create_all(bind=engine)


def _ensure_legacy_columns():
    """轻量迁移旧版 SQLite，避免升级后要求用户删除历史数据。"""
    migrations = {
        "firmware": {
            "board": "VARCHAR(255) NOT NULL DEFAULT ''",
            "board_variant": "VARCHAR(255) NOT NULL DEFAULT ''",
        },
        "FirmwareWaitCompiled": {
            "board": "VARCHAR(255) NOT NULL DEFAULT ''",
            "board_variant": "VARCHAR(255) NOT NULL DEFAULT ''",
        },
    }
    with engine.begin() as connection:
        for table_name, columns in migrations.items():
            rows = connection.execute(text(f'PRAGMA table_info("{table_name}")')).fetchall()
            existing = {row[1] for row in rows}
            for column_name, definition in columns.items():
                if column_name not in existing:
                    connection.execute(
                        text(
                            f'ALTER TABLE "{table_name}" ADD COLUMN '
                            f'"{column_name}" {definition}'
                        )
                    )


_ensure_legacy_columns()

if __name__ == '__main__':
    # 依赖函数，用于获取数据库会话
    def get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    db = get_db()


