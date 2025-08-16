"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.
"""

import time
import queue
import threading
import subprocess
from enum import Enum
from typing import Optional
from dataclasses import dataclass

class ExecutionMode(Enum):
    SYNCHRONOUS = "synchronous"
    BACKGROUND = "background"
    BACKGROUND_WAIT = "background_wait"

class TaskStatus(Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    TERMINATED = "terminated"
    
@dataclass
class TaskResult:
    task_id: str
    command: str
    status: TaskStatus
    return_code: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    start_time: float = 0
    end_time: Optional[float] = None
    execution_time: Optional[float] = None
    
class BackgroundTask:
    def __init__(self, task_id: str, command: str, process: subprocess.Popen, thread: threading.Thread):
        self.task_id = task_id
        self.command = command
        self.process = process
        self.thread = thread
        self.start_time = time.time()
        self.result_queue = queue.Queue()
        self.completed = threading.Event()
        self.terminated = False
        self.channels = None