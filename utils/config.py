# !/usr/bin/env python
# -*- coding:utf-8 -*-
# project name: compile-mpy-firmware
# author: "Lei Yong"
# creation time: 2023-11-28 17:38
# Email: leiyong711@163.com

import os
import threading
from utils.log import lg
import ruamel.yaml.scanner
from utils import constants
from ruamel.yaml import YAML
from jsonpath import jsonpath


def singleton(cls):
    instances = {}
    lock = threading.Lock()

    def wrapper(*args, **kwargs):
        if cls not in instances:
            with lock:
                if cls not in instances:
                    instances[cls] = cls(*args, **kwargs)
        return instances[cls]
    return wrapper


@singleton
class Config:

    def __init__(self, custom_config=False) -> None:
        """
        :param custom_config:   是否使用自定义配置，默认使用 static/default.yml 中的默认配置
        """
        self.config = {}
        self.config_path = None
        self.custom_config = custom_config
        self.get_config_path()
        self.reload(res=False)
        self.lock = threading.Lock()

    def get_config_path(self) -> None:
        """
        获取配置文件路径
        """
        # 默认配置文件路径
        self.config_path = constants.getDefaultConfigPath()

        # 使用自定义配置
        if self.custom_config:
            # 配置文件是否存在
            if not os.path.exists(constants.getConfigPath()):
                # 配置文件路径不存在，创建配置文件路径
                if not os.path.exists(f"{constants.CONFIG_PATH}"):
                    os.mkdir(constants.CONFIG_PATH)

                lg.warning(
                    f"自定义配置文件不存在，正在创建自定义配置文件，路径: {constants.CONFIG_PATH}/{constants.CUSTOM_CONFIG_NAME}")
                # 复制默认配置文件
                constants.newConfig()
            # 自定义配置文件路径
            self.config_path = constants.getConfigPath()
            lg.warning(f"使用自定义配置文件，路径: {self.config_path}")

    def _load_config(self) -> dict:
        yaml = YAML()
        self.get_config_path()
        try:
            with open(self.config_path, "r", encoding="utf-8") as fp:
                yconfig = yaml.load(fp)
            return yconfig
        except FileNotFoundError:
            lg.error("配置文件不存在")
            exit(1)
        except ruamel.yaml.scanner.ScannerError:
            lg.error("配置文件格式错误")
            exit(1)

    def reload(self, res=True) -> bool:
        """
        重新加载配置
        """
        try:
            self.config = self._load_config()
            if res:
                lg.info(f"配置文件已更新")
            return True
        except:
            return False

    def get(self, key: str, default=None, warn=False):
        """
        读取配置
        :param key:
        :param default:     默认值（可选）
        :param warn:        不存在该配置时，是否告警
        :return:            这个配置的值。如果没有该配置，则提供一个默认值
        """
        if key not in self.config:
            if warn:
                lg.warning(f"配置文件中不存在 {key} 配置项")
            return default
        return self.config.get(key, default)

    def get_jsonpath(self, key: str, default=None, warn=False):
        """
        使用 jsonpath 读取配置
        :param key:         $.key
        :param default:     默认值（可选）
        :param warn:        不存在该配置时，是否告警
        :return:            这个配置的值。如果没有该配置，则提供一个默认值
        """
        data = jsonpath(self.config, key)
        if not isinstance(data, list):
            if warn:
                lg.warning(f"配置文件中不存在 {key} 配置项")
            return default
        return data[0]

    def has(self, key: str) -> bool:
        """
        判断配置里是否包含某个配置项
        :param item: 配置项名
        :returns: True: 包含; False: 不包含
        """
        return key in self.config

    def update_yaml(self, data: dict) -> None:
        """
        更新配置文件，不会覆盖原有配置及注释
        """
        with self.lock:
            yaml = YAML()
            with open(self.config_path, "w", encoding="utf-8") as fp:
                yaml.dump(data, fp)
            self.reload()


if __name__ == '__main__':
    cfg = Config()
    echo = cfg.get_jsonpath("$.robot_manager", 123)

    # # 增加配置项
    # cfg.config.update({"email": {"password":  None}})
    # # 更新配置文件
    # cfg.update_yaml(cfg.config)

    lg.warning(echo)
