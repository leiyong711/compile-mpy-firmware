# !/usr/bin/env python
# -*- coding:utf-8 -*-
# project name: compile-mpy-firmware
# author: "Lei Yong"
# creation time: 2023-11-28 17:38
# Email: leiyong711@163.com

import os
import shutil
from utils.log import lg

# 主目录
APP_PATH = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)
)

LIB_PATH = os.path.join(APP_PATH, "compile-mpy-firmware")
DATA_PATH = os.path.join(APP_PATH, "static")
TEMP_PATH = os.path.join(APP_PATH, "temp")
TEMPLATE_PATH = os.path.join(APP_PATH, "server", "templates")
PLUGIN_PATH = os.path.join(APP_PATH, "plugins")
DEFAULT_CONFIG_NAME = "default.yml"
CUSTOM_CONFIG_NAME = "config.yml"

CONFIG_PATH = os.path.expanduser(os.getenv("PLUGIN_CONFIG", "~/.compile-mpy-firmware"))
CONTRIB_PATH = os.path.expanduser(os.getenv("PLUGIN_CONFIG", "~/.compile-mpy-firmware/contrib"))
CUSTOM_PATH = os.path.expanduser(os.getenv("PLUGIN_CONFIG", "~/.compile-mpy-firmware/custom"))


# lg.debug(f"APP_PATH: {APP_PATH}")
# lg.debug(f"LIB_PATH: {LIB_PATH}")
# lg.debug(f"DATA_PATH: {DATA_PATH}")
# lg.debug(f"TEMP_PATH: {TEMP_PATH}")
# lg.debug(f"TEMPLATE_PATH: {TEMPLATE_PATH}")
# lg.debug(f"PLUGIN_PATH: {PLUGIN_PATH}")
# lg.debug(f"DEFAULT_CONFIG_NAME: {DEFAULT_CONFIG_NAME}")
# lg.debug(f"CUSTOM_CONFIG_NAME: {CUSTOM_CONFIG_NAME}")
# lg.debug(f"CONFIG_PATH: {CONFIG_PATH}")
# lg.debug(f"CONTRIB_PATH: {CONTRIB_PATH}")
# lg.debug(f"CUSTOM_PATH: {CUSTOM_PATH}")


def getConfigPath():
    """
    获取配置文件的路径

    returns: 配置文件的存储路径
    """
    return os.path.join(CONFIG_PATH, CUSTOM_CONFIG_NAME)


def getQAPath():
    """
    获取QA数据集文件的路径

    returns: QA数据集文件的存储路径
    """
    qa_source = os.path.join(DATA_PATH, "qa.csv")
    qa_dst = os.path.join(CONFIG_PATH, "qa.csv")
    if not os.path.exists(qa_dst):
        shutil.copyfile(qa_source, qa_dst)
    return qa_dst


def getConfigData(*fname):
    """
    获取配置目录下的指定文件的路径

    :param *fname: 指定文件名。如果传多个，则自动拼接
    :returns: 配置目录下的某个文件的存储路径
    """
    return os.path.join(CONFIG_PATH, *fname)


def getData(*fname):
    """
    获取资源目录下指定文件的路径

    :param *fname: 指定文件名。如果传多个，则自动拼接
    :returns: 配置文件的存储路径
    """
    return os.path.join(DATA_PATH, *fname)


def getDefaultConfigPath():
    return getData(DEFAULT_CONFIG_NAME)


def newConfig():
    shutil.copyfile(getDefaultConfigPath(), getConfigPath())


def getHotwordModel(fname):
    if os.path.exists(getData(fname)):
        return getData(fname)
    else:
        return getConfigData(fname)
