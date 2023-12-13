# !/usr/bin/env python
# -*- coding:utf-8 -*-
# project name: compile-mpy-firmware
# author: "Lei Yong" 
# creation time: 2023-11-28 21:11
# Email: leiyong711@163.com

from utils import constants
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, scoped_session#, session, Session


SQLALCHEMY_DATABASE_URL = f"sqlite:///{constants.APP_PATH}/firmware.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    echo=False,  # 显示日志
    connect_args={'check_same_thread': False}  # 解决Sqlite多线程读写文件
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()



