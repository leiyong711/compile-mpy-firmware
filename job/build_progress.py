"""编译进度持久化、输出解析和实时命令执行。"""

import datetime
import os
import queue
import re
import signal
import subprocess
import threading
import time
from typing import Callable, Optional, Tuple

from app.v1.firmware.db_model import FirmwareBuildProgress
from dbs.sqlite_connect import SessionLocal
from utils.log import lg


def set_progress(
    task_id: int,
    percentage: int,
    stage: str,
    message: str,
    status: str = "running",
    current_step: int = 0,
    total_steps: int = 0,
) -> None:
    percentage = max(0, min(100, int(percentage)))
    session = SessionLocal()
    try:
        progress = session.query(FirmwareBuildProgress).filter_by(task_id=task_id).first()
        if progress is None:
            progress = FirmwareBuildProgress(task_id=task_id)
            session.add(progress)
        progress.percentage = percentage
        progress.stage = stage
        progress.message = message[:512]
        progress.status = status
        progress.current_step = current_step
        progress.total_steps = total_steps
        progress.updated_at = datetime.datetime.now()
        session.commit()
    except Exception:
        session.rollback()
        lg.exception("保存编译进度失败")
    finally:
        session.close()


def get_progress(task_id: int) -> Optional[dict]:
    session = SessionLocal()
    try:
        progress = session.query(FirmwareBuildProgress).filter_by(task_id=task_id).first()
        return progress.to_dict() if progress else None
    finally:
        session.close()


class BuildOutputParser:
    """ESP32 使用 Ninja 的 n/total；ESP8266 使用 make 预扫描后的动作总数。"""

    _ninja = re.compile(r"^\[(\d+)/(\d+)\]")
    _make_action = re.compile(r"^(?:CC|CXX|AS|LINK|GEN|Create)\s")

    def __init__(self, task_id: int, device_type: str, total_steps: int = 0):
        self.task_id = task_id
        self.device_type = device_type
        self.total_steps = total_steps
        self.current_step = 0
        self.last_percentage = -1
        self.ninja_total = 0

    def feed(self, line: str) -> None:
        line = line.strip()
        if not line:
            return
        current = total = 0
        if self.device_type == "ESP8266":
            if not self._make_action.match(line):
                return
            self.current_step += 1
            current = self.current_step
            total = max(self.total_steps, current)
        else:
            match = self._ninja.match(line)
            if not match:
                return
            current, total = (int(value) for value in match.groups())
            # ESP-IDF 会嵌套启动 bootloader Ninja（例如主任务 1221 步、
            # bootloader 102 步）。只跟踪最大的主构建分母，避免进度倒退。
            if total > self.ninja_total:
                self.ninja_total = total
            elif total < self.ninja_total:
                return

        percentage = 10 + round((current / max(total, 1)) * 85)
        if percentage <= self.last_percentage:
            return
        self.last_percentage = percentage
        set_progress(
            self.task_id,
            percentage,
            "building",
            line,
            current_step=current,
            total_steps=total,
        )


def run_streaming_command(
    command: str,
    timeout_seconds: int,
    on_line: Optional[Callable[[str], None]] = None,
) -> Tuple[bool, str]:
    """逐行读取 stdout/stderr，既不丢错误信息，也不会阻塞 WebSocket。"""
    process = subprocess.Popen(
        ["/bin/bash", "-lc", command],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        start_new_session=True,
    )
    output_queue: queue.Queue = queue.Queue()

    def read_output() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            output_queue.put(line)
        output_queue.put(None)

    reader = threading.Thread(target=read_output, daemon=True)
    reader.start()
    started_at = time.monotonic()
    output = []
    finished_reading = False

    try:
        while not finished_reading:
            if time.monotonic() - started_at > timeout_seconds:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                return False, "命令执行超时（{} 秒）\n{}".format(
                    timeout_seconds, "".join(output[-200:])
                )
            try:
                item = output_queue.get(timeout=0.25)
            except queue.Empty:
                continue
            if item is None:
                finished_reading = True
                continue
            output.append(item)
            if on_line:
                on_line(item)
        return_code = process.wait(timeout=10)
    except Exception:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
        raise

    result = "".join(output)
    if return_code != 0:
        lg.error("编译命令返回 {}：\n{}", return_code, result[-8000:])
        return False, result
    return True, result


def estimate_esp8266_steps(command: str) -> int:
    """make -n 会列出真实将执行的动作，用它作为 ESP8266 的精确分母。"""
    try:
        result = subprocess.run(
            ["/bin/bash", "-lc", command],
            timeout=180,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return len(
            re.findall(r'^echo "(?:CC|CXX|AS|LINK|GEN|Create)\s', result.stdout, re.MULTILINE)
        )
    except (subprocess.SubprocessError, OSError):
        lg.exception("预估 ESP8266 编译步骤失败")
        return 0
