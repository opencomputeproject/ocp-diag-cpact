"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

===============================================================================
ExecutionConstants defines enums and data structures for managing task execution modes,
statuses, and results in automated systems. It supports synchronous and asynchronous
execution tracking, including background task lifecycle management.

Features:
- Defines execution modes: synchronous, background, and background with wait.
- Tracks task status: running, completed, failed, timeout, and terminated.
- Provides a structured `TaskResult` dataclass for capturing execution metadata.
- Implements `BackgroundTask` class for managing subprocess-based background tasks.

Enums:
    ExecutionMode:
        - SYNCHRONOUS: Executes and waits for completion.
        - BACKGROUND: Executes asynchronously.
        - BACKGROUND_WAIT: Executes asynchronously and waits for result.

    TaskStatus:
        - RUNNING: Task is currently executing.
        - COMPLETED: Task finished successfully.
        - FAILED: Task encountered an error.
        - TIMEOUT: Task exceeded allowed execution time.
        - TERMINATED: Task was manually stopped.

Classes:
    TaskResult:
        Captures metadata and output of a completed task.
        Includes command, status, return code, stdout, stderr, and timing info.

    BackgroundTask:
        Manages background execution using threads and subprocesses.
        Tracks task ID, command, process, thread, and completion status.

Usage:
    Use `TaskResult` to store and return execution outcomes.
    Use `BackgroundTask` to manage long-running or asynchronous operations.
    Reference `ExecutionMode` and `TaskStatus` for consistent task control logic.
===============================================================================
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
    def __init__(
        self,
        task_id: str,
        command: str,
        process: subprocess.Popen,
        thread: threading.Thread,
    ) -> None:
        """Initializes a background task."""
        self.task_id = task_id
        self.command = command
        self.process = process
        self.thread = thread
        self.start_time = time.time()
        self.result_queue = queue.Queue()
        self.completed = threading.Event()
        self.terminated = False
        self.channels = None
