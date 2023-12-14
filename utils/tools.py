# !/usr/bin/env python
# -*- coding:utf-8 -*-
# project name: compile-mpy-firmware
# author: "Lei Yong" 
# creation time: 2023-11-28 20:02
# Email: leiyong711@163.com
import hashlib
import random
import fnmatch
import re
import os
import shutil
import time
import json
import traceback
import zipfile
import requests
import datetime
import subprocess
from utils.log import lg
from jsonpath import jsonpath
import xml.etree.ElementTree as ET


def get_session(pool_connections: int = 50, pool_maxsize: int = 50, **adapter_kwargs):
    """
    创建一个带有连接池和适配器的`requests`会话对象。
    参数：
    - pool_connections: 最大连接数，默认为50。
    - pool_maxsize: 每个主机的最大连接数，默认为50。
    - **adapter_kwargs: 其他适配器参数。
    返回值：
    - 返回一个配置了连接池和适配器的`requests`会话对象。
    """
    # 创建一个`requests`会话对象
    session = requests.session()
    # 创建一个`requests`适配器对象，用于配置连接池
    adapter = requests.adapters.HTTPAdapter(
        pool_connections=pool_connections, pool_maxsize=pool_maxsize, **adapter_kwargs
    )
    # 将适配器挂载到会话对象的 'http://' 和 'https://' 前缀上
    session.mount('http://', adapter)
    session.mount('https://', adapter)

    # 返回配置了连接池和适配器的会话对象
    return session

def get_jsonpath(json_data: dict, key: str, default=None, warn=False, index_1=True):
    """
    使用 jsonpath 读取配置
    :param key:         $.key
    :param default:     默认值（可选）
    :param warn:        不存在该配置时，是否告警
    :return:            这个配置的值。如果没有该配置，则提供一个默认值
    """
    data = jsonpath(json_data, key)
    if not isinstance(data, list):
        return default
    return data[0] if index_1 else data


def check_file_existence(file_path, timeout=60, interval=0.1):
    """
    检测文件是否存在
    :param file_path:       文件路径
    :param timeout:        超时时间
    :param interval:       检测间隔
    :return:
    """
    start_time = time.time()
    while True:
        if os.path.exists(file_path):
            return True
        elapsed_time = time.time() - start_time
        if elapsed_time >= timeout:
            return False
        time.sleep(interval)  # 等待1秒后再次检测文件是否存在


def find_file(path, filename):
    """
    在指定路径下查找文件
    :param path:
    :param filename:
    :return:
    """
    # 获取路径下所有文件名
    try:
        files = os.listdir(path)
    except FileNotFoundError:
        lg.error(f"文件路径不存在：{path}")
        return ""

    # 在文件列表中查找匹配的文件名
    for file in files:
        # 判断文件名是否以给定的filename开头
        if file.startswith(filename):
            # 构建文件的完整路径
            file_path = os.path.join(path, file)
            # 返回文件路径和完整文件名
            return file_path

    # 未找到匹配的文件，返回空字符串
    return ""


def create_str_time(UTC=False):
    """获取当前时间字符串"""
    if UTC:
        temp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))
        return india_to_local(india_time_str=temp)
    else:
        return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))


def india_to_local(india_time_str, india_format='%Y-%m-%d %H:%M:%S'):
    """UTC时间转BeiJing时间"""
    india_dt = datetime.datetime.strptime(india_time_str, india_format)
    local_dt = india_dt + datetime.timedelta(hours=8)
    time_str = local_dt.strftime(india_format)
    return time_str

def compress_files(files, output_path):
    """压缩文件"""
    with zipfile.ZipFile(output_path, 'w') as zipf:
        for file in files:
            zipf.write(file, arcname=file)

def compress_folder(folder_path, output_path):
    """压缩文件夹"""
    shutil.make_archive(output_path, 'zip', folder_path)


def decompress_folder(zip_path, output_path):
    """解压缩文件"""
    shutil.unpack_archive(zip_path, output_path)


def find_files(directory, pattern, max_depth):
    """查找包含特定模式的文件，限制搜索深度"""
    matches = []
    for root, dirnames, filenames in os.walk(directory):
        # 计算当前目录的深度
        depth = root[len(directory):].count(os.sep)
        lg.debug(f"当前目录的深度：{depth}")

        # 如果当前目录的深度大于最大深度，跳过这个目录
        if depth > max_depth:
            del dirnames[:]
            continue

        lg.warning(f"当前目录{root}：{filenames} ------ {pattern}")
        for filename in fnmatch.filter(filenames, pattern):
            matches.append(os.path.join(root, filename))
    return matches


def find_dirs(directory, pattern, max_depth):
    """查找包含特定模式的目录，限制搜索深度"""
    matches = []
    for root, dirnames, _ in os.walk(directory):
        # 计算当前目录的深度
        depth = root[len(directory):].count(os.sep)

        # 如果当前目录的深度大于最大深度，跳过这个目录
        if depth > max_depth:
            del dirnames[:]
            continue

        for dirname in fnmatch.filter(dirnames, pattern):
            matches.append(os.path.join(root, dirname))
    return matches


def generate_random_number():
    """
    生成随机数
    :return:
    """
    now = datetime.datetime.now()  # 获取当前日期和时间
    timestamp = now.strftime("%Y%m%d%H%M%S%f")  # 格式化为年月日时分秒毫秒的字符串
    random_number = str(random.randint(0, 1000000))  # 生成随机数并转换为字符串
    random_number = random_number.zfill(6)  # 将随机数补足6位，不足的部分用0填充
    result = timestamp + random_number  # 将日期时间和随机数连接起来
    return result


async def sign_md5(data):
    """
    MD5加密
    :param data:
    :return:
    """
    md = hashlib.md5()
    md.update(data.encode(encoding='utf-8'))
    sign = md.hexdigest()
    lg.debug('MD5加密前：' + data)
    lg.debug('MD5加密后：' + sign)
    return sign

def excuting_command(command, timeout_seconds=60):
    """
    执行命令
    :param command:
    :param timeout_seconds:
    :return:
    """
    # lg.debug(f"执行命令：{command}")
    try:
        result = subprocess.run(command, shell=True, timeout=timeout_seconds, check=True, capture_output=True, text=True)
        return True, result.stdout
    except subprocess.TimeoutExpired:
        lg.error(f"执行超时,错误原因:\n{traceback.format_exc()}")
        return False, f"命令在 {timeout_seconds} 秒后超时"
    except subprocess.CalledProcessError as e:
        lg.error(f"执行失败,错误原因:\n{traceback.format_exc()}")
        lg.error(f"Command output: {e.output}")
        lg.error(f"Command error output: {e.stderr}")
        return False, f"命令失败并返回代码: {e.returncode}"


def excuting_command_old(command, timeout_seconds=60):
    """
    执行命令
    :param command:
    :param timeout_seconds:
    :return:
    """
    # lg.debug(f"执行命令：{command}")
    # process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    process = subprocess.Popen(command, stdout=subprocess.PIPE, shell=True, executable='/bin/bash')

    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        process.kill()
        lg.error(f"执行超时,错误原因:\n{traceback.format_exc()}")
        return False, f"Command timed out after {timeout_seconds} seconds"
    except Exception as e:
        process.kill()
        lg.error(f"执行失败,错误原因:\n{traceback.format_exc()}")
        return False, str(e)

    if process.returncode != 0:
        lg.error(f"执行失败,错误原因:\n{stderr}")
        return False, f"Command failed with return code: {process.returncode}"

    return True, stdout



if __name__ == '__main__':
    print(generate_random_number())
    decompress_folder('','')