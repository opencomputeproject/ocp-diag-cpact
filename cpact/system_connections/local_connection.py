"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

===============================================================================
LocalConnection is a utility class for executing commands and managing tasks on the local system
within automated test environments. It extends ConnectionInterface and provides synchronous and
background execution modes, file transfer simulation, and task lifecycle management.

Features:
- Executes shell commands locally with support for synchronous and background modes.
- Supports sudo execution with password injection on Unix/Linux systems.
- Simulates file upload and download operations using local paths.
- Tracks task status, output, and execution time.
- Provides task termination, cleanup, and result retrieval.
- Compatible with both Windows and Unix-like platforms.

Attributes:
    background_tasks (dict): Active background tasks indexed by task ID.
    completed_tasks (dict): Completed task results indexed by task ID.
    lock (threading.Lock): Lock for thread-safe task management.
    is_windows (bool): Indicates if the current platform is Windows.

Usage:
    Instantiate LocalConnection with optional config.
    Use `execute_command()` to run commands locally.
    Use `wait_for_task()` or `get_task_result_and_details()` to retrieve results.
    Use `terminate_task()` and `cleanup_all_tasks()` to manage task lifecycle.
===============================================================================
"""

import os
import time
import uuid
import glob
import queue
import signal
import shutil
import platform
import tempfile
import threading
import subprocess
from enum import Enum
from dataclasses import dataclass
from typing import Dict, Optional, Tuple, List, Any

from cpact.system_connections.base_connection import ConnectionInterface
from cpact.system_connections.constants import (
    ExecutionMode,
    TaskStatus,
    TaskResult,
    BackgroundTask,
)


class LocalConnection(ConnectionInterface):
    def __init__(self, config: Dict[str, Any] = None) -> None:
        super().__init__(config=config)
        self.background_tasks: Dict[str, BackgroundTask] = {}
        self.completed_tasks: Dict[str, TaskResult] = {}
        self.lock = threading.Lock()
        self.is_windows = platform.system().lower() == "windows"

    def connect(self) -> bool:
        return super().connect()

    def download_file(self, remote_path: str, local_path: str) -> bool:
        """Download a file from the local system (simulated for local connection)."""
        if not os.path.exists(remote_path):
            self.logger.error(f"Remote file {remote_path} does not exist.")
            return False

        try:
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            shutil.copy2(remote_path, local_path)
            return True
        except Exception as e:
            self.logger.error(f"Failed to download file: {e}")
            return False

    def upload_file(self, local_path: str, remote_path: str) -> bool:
        """Upload a file to the local system (simulated for local connection)."""
        if not os.path.exists(local_path):
            self.logger.error(f"Local file {local_path} does not exist.")
            return False

        try:
            os.makedirs(os.path.dirname(remote_path), exist_ok=True)
            shutil.copy2(local_path, remote_path)
            return True
        except Exception as e:
            self.logger.error(f"Failed to upload file: {e}")
            return False

    def list_files(self, path_or_pattern: str) -> List[str]:
        """Enumerate regular files under a local path, directory or glob pattern."""
        try:
            matches = glob.glob(path_or_pattern)
        except Exception as e:
            self.logger.error(f"Failed to expand '{path_or_pattern}': {e}")
            return []

        files: List[str] = []
        for match in matches:
            if os.path.isfile(match):
                files.append(os.path.abspath(match))
            elif os.path.isdir(match):
                for root, _, names in os.walk(match):
                    files.extend(os.path.abspath(os.path.join(root, n))
                                 for n in names)
        return sorted(set(files))

    def disconnect(self) -> None:
        """Disconnect method for LocalConnection."""
        # No specific disconnect logic needed for local connections
        pass

    def is_connected(self) -> bool:
        """Check if the connection is established."""
        # For local connections, we assume it's always connected
        return True

    def _prepare_command(
        self, command: str, is_sudo: bool = False, sudo_password: Optional[str] = None
    ) -> Tuple[Any, bool]:
        """Prepare command for execution based on the operating system.

        Returns the command to hand to Popen and the ``shell`` flag to use with
        it. On Windows we never ask Popen for a shell: complex commands already
        get an explicit ``cmd /c`` wrapper here, so letting Popen add a second
        cmd.exe would only break quoting.
        """
        if self.is_windows:
            if is_sudo:
                self.logger.warning(
                    "Sudo commands are not supported on Windows. Running as regular command."
                )

            if "&&" in command or "||" in command or "|" in command:
                # Explicit cmd.exe invocation for complex shell operations.
                return f'cmd /c "{command}"', False
            else:
                return command, False
        else:
            # Unix/Linux handling
            if is_sudo and sudo_password:
                return ["sudo", "-S"] + command.split(), False
            else:
                # A bare string needs shell=True on POSIX, otherwise Popen
                # treats the entire string as the executable name.
                return command, True

    def execute_command(
        self,
        command: str,
        mode: ExecutionMode = ExecutionMode.SYNCHRONOUS,
        sudo_password: Optional[str] = None,
        timeout: Optional[float] = None,
        wait: bool = False,
        shell: bool = True,
        use_sudo: bool = False
    ) -> Optional[TaskResult]:
        """
        Execute a command based on the specified execution mode.

        Args:
            command: The command to execute
            mode: ExecutionMode enum (SYNCHRONOUS, BACKGROUND, BACKGROUND_WAIT)
            sudo_password: Password for sudo commands (if needed)
            timeout: Timeout in seconds
            wait: If True with background mode, wait for completion after timeout
            shell: Whether to use shell for command execution

        Returns:
            TaskResult for synchronous/background_wait execution,
            task_id for background execution when wait=False,
            None for background execution when wait=True but timeout exceeded
        """
        task_id = str(uuid.uuid4())

        # Process command and determine if it needs sudo
        is_sudo_command = command.strip().startswith("sudo")
        if is_sudo_command and sudo_password:
            # Remove 'sudo' from command, we'll handle it in subprocess
            actual_command = command[4:].strip()
        else:
            actual_command = command

        # Prepare command for the current OS
        prepared_command, use_shell = self._prepare_command(
            actual_command, is_sudo_command, sudo_password
        )
        self.logger.debug(
            f"Prepared command: {prepared_command}, use_shell: {use_shell}, timeout: {timeout}"
        )

        if mode == ExecutionMode.SYNCHRONOUS:
            return self._execute_synchronous(
                task_id,
                prepared_command,
                timeout,
                use_shell,
                is_sudo_command,
                sudo_password,
            )

        elif mode == ExecutionMode.BACKGROUND:
            self._execute_background(
                task_id, prepared_command, use_shell, is_sudo_command, sudo_password
            )
            if wait and timeout is not None:
                # Wait for the specified timeout, then return result
                return self.wait_for_task(task_id, timeout)
            else:
                # Return task_id for tracking
                return TaskResult(
                    task_id=task_id,
                    command=command,
                    status=TaskStatus.RUNNING,
                    start_time=time.time(),
                )

        elif mode == ExecutionMode.BACKGROUND_WAIT:
            self._execute_background(
                task_id, prepared_command, use_shell, is_sudo_command, sudo_password
            )
            # Always wait for completion in this mode
            return self.wait_for_task(task_id, timeout)

    def _execute_synchronous(
        self,
        task_id: str,
        command: Any,
        timeout: Optional[float],
        shell: bool,
        is_sudo: bool = False,
        sudo_password: Optional[str] = None,
    ) -> TaskResult:
        """Execute a command synchronously and return the result.

        Output goes to temporary files rather than pipes. A pipe only reaches
        EOF once *every* process holding the write handle has exited, so a tool
        that spawns a helper which outlives it leaves ``communicate()`` blocked
        forever even after the tool itself returned 0. Files have no such
        dependency, and they preserve partial output when a command is killed
        on timeout.
        """
        start_time = time.time()
        result = TaskResult(
            task_id=task_id,
            command=str(command),
            status=TaskStatus.RUNNING,
            start_time=start_time,
        )

        tmp_dir = tempfile.mkdtemp(prefix="cpact_cmd_")
        stdout_path = os.path.join(tmp_dir, "stdout.log")
        stderr_path = os.path.join(tmp_dir, "stderr.log")
        process = None

        try:
            with open(stdout_path, "wb") as out_f, open(stderr_path, "wb") as err_f:
                popen_kwargs: Dict[str, Any] = {
                    "stdout": out_f,
                    "stderr": err_f,
                    "shell": shell,
                }

                if is_sudo and sudo_password and not self.is_windows:
                    # Keep stdin open so the sudo password can be injected.
                    popen_kwargs["stdin"] = subprocess.PIPE
                    popen_kwargs["text"] = True
                else:
                    # Never inherit the parent's stdin: a tool that prompts for
                    # input would otherwise block until the timeout fires.
                    popen_kwargs["stdin"] = subprocess.DEVNULL

                if self.is_windows:
                    # Own process group, so the whole tree can be killed later.
                    popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
                else:
                    popen_kwargs["start_new_session"] = True

                process = subprocess.Popen(command, **popen_kwargs)

                if popen_kwargs["stdin"] == subprocess.PIPE and process.stdin:
                    try:
                        process.stdin.write(f"{sudo_password}\n")
                        process.stdin.flush()
                    finally:
                        process.stdin.close()

                try:
                    result.return_code = process.wait(timeout=timeout)
                    result.status = (
                        TaskStatus.COMPLETED
                        if result.return_code == 0
                        else TaskStatus.FAILED
                    )
                except subprocess.TimeoutExpired:
                    self.logger.error(
                        f"Command timed out after {timeout}s, killing process tree: {command}"
                    )
                    self._kill_process_tree(process)
                    result.status = TaskStatus.TIMEOUT
                    result.return_code = -1

            result.stdout = self._read_output_file(stdout_path)
            result.stderr = self._read_output_file(stderr_path)

            if result.status == TaskStatus.TIMEOUT:
                result.stderr = (
                    f"{result.stderr}\n"
                    f"[cpact] Command exceeded the step 'duration' of {timeout}s "
                    f"and its process tree was terminated."
                ).strip()

        except Exception as e:
            self.logger.error(f"Failed to execute command {command}: {e}")
            if process is not None:
                self._kill_process_tree(process)
            result.status = TaskStatus.FAILED
            result.stderr = str(e)
            result.return_code = -1
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

        result.end_time = time.time()
        result.execution_time = result.end_time - result.start_time

        return result

    @staticmethod
    def _read_output_file(path: str, limit: int = 50 * 1024 * 1024) -> str:
        """Read a captured output file, tolerating undecodable bytes."""
        try:
            with open(path, "rb") as f:
                data = f.read(limit)
            return data.decode("utf-8", errors="replace")
        except OSError:
            return ""

    def _kill_process_tree(self, process: subprocess.Popen) -> None:
        """Kill a process *and every process it spawned*.

        ``Popen.kill()`` only signals the direct child. Grandchildren keep
        running and keep inherited handles open, which is what makes a
        timed-out step impossible to clean up.
        """
        if process.poll() is not None:
            return

        try:
            if self.is_windows:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=30,
                    check=False,
                )
            else:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except Exception as e:
            self.logger.warning(
                f"Process tree kill failed for pid {process.pid}: {e}")

        # Make sure the direct child is gone and reaped either way.
        try:
            process.kill()
        except Exception:
            pass
        try:
            process.wait(timeout=10)
        except Exception:
            self.logger.warning(
                f"Process {process.pid} did not exit after kill")

    def _execute_background(
        self,
        task_id: str,
        command: str,
        shell: bool,
        is_sudo: bool = False,
        sudo_password: Optional[str] = None,
    ) -> None:
        """Execute command in background thread."""
        try:
            if is_sudo and sudo_password and not self.is_windows:
                # Handle sudo commands on Unix/Linux
                process = subprocess.Popen(
                    command,  # command is already prepared as list for sudo
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            else:
                # Handle regular commands (Windows and Unix)
                process = subprocess.Popen(
                    command,
                    shell=shell,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if self.is_windows else 0,
                )

            thread = threading.Thread(
                target=self._background_worker,
                args=(task_id, str(command), process, is_sudo, sudo_password),
                daemon=True,
            )

            background_task = BackgroundTask(
                task_id, str(command), process, thread)

            with self.lock:
                self.background_tasks[task_id] = background_task

            thread.start()
            self.logger.info(f"Started background task {task_id}: {command}")

        except Exception as e:
            self.logger.error(
                f"Failed to start background task {task_id}: {e}")
            result = TaskResult(
                task_id=task_id,
                command=str(command),
                status=TaskStatus.FAILED,
                stderr=str(e),
                return_code=-1,
                start_time=time.time(),
            )
            with self.lock:
                self.completed_tasks[task_id] = result

    def _background_worker(
        self,
        task_id: str,
        command: str,
        process: subprocess.Popen,
        is_sudo: bool = False,
        sudo_password: Optional[str] = None,
    ) -> None:
        """Worker function for background task execution."""
        start_time = time.time()

        try:
            if is_sudo and sudo_password and not self.is_windows:
                # For sudo commands on Unix/Linux, send password via stdin
                stdout, stderr = process.communicate(
                    input=f"{sudo_password}\n")
            else:
                # For regular commands or Windows
                stdout, stderr = process.communicate()

            result = TaskResult(
                task_id=task_id,
                command=command,
                status=(
                    TaskStatus.COMPLETED
                    if process.returncode == 0
                    else TaskStatus.FAILED
                ),
                return_code=process.returncode,
                stdout=stdout,
                stderr=stderr,
                start_time=start_time,
                end_time=time.time(),
            )
            result.execution_time = result.end_time - result.start_time

        except Exception as e:
            result = TaskResult(
                task_id=task_id,
                command=command,
                status=TaskStatus.FAILED,
                return_code=-1,
                stderr=str(e),
                start_time=start_time,
                end_time=time.time(),
            )
            result.execution_time = result.end_time - result.start_time

        # Move task to completed tasks
        with self.lock:
            if task_id in self.background_tasks:
                background_task = self.background_tasks[task_id]
                background_task.result_queue.put(result)
                background_task.completed.set()
                del self.background_tasks[task_id]
                self.completed_tasks[task_id] = result

        self.logger.info(
            f"Background task {task_id} completed with status: {result.status}"
        )

    def wait_for_task(
        self, task_id: str, timeout: Optional[float] = None
    ) -> Optional[TaskResult]:
        """
        Wait for a specific background task to complete.

        Args:
            task_id: ID of the task to wait for
            timeout: Maximum time to wait in seconds

        Returns:
            TaskResult if task completes, None if timeout or task not found
        """
        try:
            if hasattr(task_id, "task_id"):
                actual_task_id = task_id.task_id
            else:
                actual_task_id = str(task_id)

            with self.lock:
                if actual_task_id in self.completed_tasks:
                    return self.completed_tasks[actual_task_id]

                if actual_task_id not in self.background_tasks:
                    self.logger.warning(f"Task {actual_task_id} not found")
                    return None

                background_task = self.background_tasks[actual_task_id]

            # Wait for completion outside the lock
            if background_task.completed.wait(timeout=timeout):
                try:
                    return background_task.result_queue.get_nowait()
                except queue.Empty:
                    # Check completed tasks again
                    with self.lock:
                        return self.completed_tasks.get(actual_task_id)
            try:
                return background_task.result_queue.get_nowait()
            except queue.Empty:
                with self.lock:
                    if actual_task_id in self.completed_tasks:
                        return self.completed_tasks[actual_task_id]

                    # If still not in completed tasks, create a timeout result with partial data
                    # Try to get any partial output that might be available
                    partial_stdout = ""
                    partial_stderr = ""

                    # Create timeout result
                    result = TaskResult(
                        task_id=actual_task_id,
                        command=background_task.command,
                        status=TaskStatus.TIMEOUT,
                        return_code=-1,
                        stdout=partial_stdout,
                        stderr=f"Task timed out after {timeout} seconds",
                        start_time=background_task.start_time,
                        end_time=time.time(),
                    )
                    result.execution_time = result.end_time - result.start_time

                    self.completed_tasks[actual_task_id] = result
                    return result
        except Exception as e:
            self.logger.error(f"Error waiting for task {task_id}: {e}")
            # Even on error, try to return something useful
            actual_task_id = (
                str(task_id) if not hasattr(
                    task_id, "task_id") else task_id.task_id
            )
            return TaskResult(
                task_id=actual_task_id,
                command=f"Unknown command for {actual_task_id}",
                status=TaskStatus.FAILED,
                return_code=-1,
                stdout="",
                stderr=f"Error waiting for task: {e}",
                start_time=time.time(),
                end_time=time.time(),
                execution_time=0,
            )
            # Timeout occurred
            # self.logger.warning(f"Timeout waiting for task {actual_task_id}")
            # return None

        except Exception as e:
            self.logger.error(f"Error waiting for task {actual_task_id}: {e}")
            return None

    def wait_for_all_tasks(
        self, timeout: Optional[float] = None
    ) -> Dict[str, TaskResult]:
        """
        Wait for all background tasks to complete.

        Args:
            timeout: Maximum time to wait for all tasks

        Returns:
            Dictionary of task_id -> TaskResult for all tasks
        """
        start_time = time.time()
        results = {}

        # Get snapshot of current background tasks
        with self.lock:
            task_ids = list(self.background_tasks.keys())
            # Also include already completed tasks
            results.update(self.completed_tasks)

        for task_id in task_ids:
            remaining_timeout = None
            if timeout is not None:
                elapsed = time.time() - start_time
                remaining_timeout = max(0, timeout - elapsed)
                if remaining_timeout <= 0:
                    break

            result = self.wait_for_task(task_id, remaining_timeout)
            if result:
                results[task_id] = result

        return results

    def get_task_result_and_details(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Get comprehensive task details including result if completed.

        Args:
            task_id: ID of the task

        Returns:
            Dictionary with task details and result, or None if not found
        """
        if hasattr(task_id, "task_id"):
            actual_task_id = task_id.task_id
        else:
            actual_task_id = str(task_id)
        with self.lock:
            # Check completed tasks first
            if actual_task_id in self.completed_tasks:
                result = self.completed_tasks[actual_task_id]
                return {
                    "task_id": actual_task_id,
                    "command": result.command,
                    "status": result.status.value,
                    "return_code": result.return_code,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "start_time": result.start_time,
                    "end_time": result.end_time,
                    "execution_time": result.execution_time,
                    "is_running": False,
                    "has_result": True,
                }

            # Check running tasks
            if actual_task_id in self.background_tasks:
                background_task = self.background_tasks[actual_task_id]
                return {
                    "task_id": actual_task_id,
                    "command": background_task.command,
                    "status": TaskStatus.RUNNING.value,
                    "return_code": None,
                    "stdout": "",
                    "stderr": "",
                    "start_time": background_task.start_time,
                    "end_time": None,
                    "execution_time": None,
                    "current_runtime": time.time() - background_task.start_time,
                    "is_running": True,
                    "has_result": False,
                }

        return None

    def wait_for_task_with_details(
        self, task_id: str, timeout: Optional[float] = None, wait: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        Wait for a specific background task and get detailed result.

        Args:
            task_id: ID of the task to wait for
            timeout: Maximum time to wait in seconds
            wait: If True, wait for completion; if False, return current status

        Returns:
            Dictionary with task details and result, None if timeout or task not found
        """
        if hasattr(task_id, "task_id"):
            actual_task_id = task_id.task_id
        else:
            actual_task_id = str(task_id)
        if not wait:
            return self.get_task_result_and_details(actual_task_id)

        # Wait for task completion
        result = self.wait_for_task(actual_task_id, timeout)

        if result is None:
            # Task didn't complete within timeout, return current details
            details = self.get_task_result_and_details(actual_task_id)
            if details:
                details["timeout_exceeded"] = True
            return ("", f"Task {actual_task_id} returned None result", -1, "error")

        # Return comprehensive details with result
        # return self.get_task_result_and_details(actual_task_id)

        # Return result as tuple
        return (result.stdout, result.stderr, result.return_code, result.status.value)

    def get_all_tasks(self) -> Dict[str, Dict[str, Any]]:
        """Get details of all tasks (running and completed)."""
        all_tasks = {}

        try:
            with self.lock:
                # Add running tasks
                for task_id, background_task in self.background_tasks.items():
                    all_tasks[task_id] = {
                        "task_id": task_id,
                        "command": background_task.command,
                        "status": TaskStatus.RUNNING.value,
                        "start_time": background_task.start_time,
                        "current_runtime": time.time() - background_task.start_time,
                        "is_running": True,
                        "has_result": False,
                    }

                # Add completed tasks
                for task_id, result in self.completed_tasks.items():
                    all_tasks[task_id] = {
                        "task_id": task_id,
                        "command": result.command,
                        "status": result.status.value,
                        "return_code": result.return_code,
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                        "start_time": result.start_time,
                        "end_time": result.end_time,
                        "execution_time": result.execution_time,
                        "is_running": False,
                        "has_result": True,
                    }
        except Exception as e:
            self.logger.error(f"Error getting all tasks: {e}")

        return all_tasks

    def terminate_task(self, task_id: str) -> bool:
        """
        Terminate a running background task.

        Args:
            task_id: ID of the task to terminate

        Returns:
            True if task was terminated, False if not found or already completed
        """
        if hasattr(task_id, "task_id"):
            actual_task_id = task_id.task_id
        else:
            actual_task_id = str(task_id)
        with self.lock:
            if actual_task_id not in self.background_tasks:
                self.logger.warning(
                    f"Task {actual_task_id} not found or already completed"
                )
                return False

            background_task = self.background_tasks[actual_task_id]

        try:
            self._kill_process_tree(background_task.process)
            # Give it a moment to terminate gracefully
            time.sleep(0.1)

            if background_task.process.poll() is None:
                # Force kill if still running
                background_task.process.kill()

            # Create termination result
            result = TaskResult(
                task_id=actual_task_id,
                command=background_task.command,
                status=TaskStatus.TERMINATED,
                return_code=-1,
                start_time=background_task.start_time,
                end_time=time.time(),
                stderr="Task was terminated",
            )
            result.execution_time = result.end_time - result.start_time

            with self.lock:
                if actual_task_id in self.background_tasks:
                    del self.background_tasks[actual_task_id]
                self.completed_tasks[actual_task_id] = result

            self.logger.info(f"Terminated task {actual_task_id}")
            return True

        except Exception as e:
            self.logger.error(
                f"Failed to terminate task {actual_task_id}: {e}")

            # Even if termination failed, create a terminated result to ensure we return something
            try:
                result = TaskResult(
                    task_id=actual_task_id,
                    command=background_task.command,
                    status=TaskStatus.TERMINATED,
                    return_code=-1,
                    start_time=background_task.start_time,
                    end_time=time.time(),
                    stdout="",  # No partial output available in this case
                    stderr=f"Task termination failed: {str(e)}",
                )
                result.execution_time = result.end_time - result.start_time

                # Force move to completed tasks
                with self.lock:
                    if actual_task_id in self.background_tasks:
                        del self.background_tasks[actual_task_id]
                    self.completed_tasks[actual_task_id] = result

            except Exception as cleanup_error:
                self.logger.error(
                    f"Failed to create terminated result: {cleanup_error}"
                )

            return False

    def terminate_all_tasks(self) -> List[str]:
        """
        Terminate all running background tasks.

        Returns:
            List of task IDs that were terminated
        """
        with self.lock:
            task_ids = list(self.background_tasks.keys())

        terminated = []
        for task_id in task_ids:
            if self.terminate_task(task_id):
                terminated.append(task_id)

        return terminated

    def get_task_output(self, task_id: str) -> Optional[TaskResult]:
        """
        Get output of a completed task and optionally remove it from completed tasks.

        Args:
            task_id: ID of the task

        Returns:
            TaskResult if found, None otherwise
        """
        if hasattr(task_id, "task_id"):
            actual_task_id = task_id.task_id
        else:
            actual_task_id = str(task_id)
        with self.lock:
            return self.completed_tasks.get(actual_task_id)

    def close_task(self, task_id: str) -> bool:
        """
        Remove a completed task from the completed tasks list.

        Args:
            task_id: ID of the task to close

        Returns:
            True if task was closed, False if not found
        """
        with self.lock:
            if task_id in self.completed_tasks:
                del self.completed_tasks[task_id]
                self.logger.info(f"Closed task {task_id}")
                return True
            return False

    def close_all_completed_tasks(self) -> List[str]:
        """
        Remove all completed tasks from memory.

        Returns:
            List of task IDs that were closed
        """
        with self.lock:
            closed_task_ids = list(self.completed_tasks.keys())
            self.completed_tasks.clear()

        self.logger.info(f"Closed {len(closed_task_ids)} completed tasks")
        return closed_task_ids

    def cleanup_task(self, task_id: str):
        """Clean up task resources (compatibility method)"""
        # Ensure task_id is a string
        if hasattr(task_id, "task_id"):
            actual_task_id = task_id.task_id
        else:
            actual_task_id = str(task_id)

        self.close_task(actual_task_id)

    def cleanup_all_tasks(self) -> int:
        """Clean up all tasks (completed and running) (compatibility method)"""
        # First terminate any running tasks
        terminated = self.terminate_all_tasks()

        # Clean up all tasks
        closed = self.close_all_completed_tasks()

        return len(terminated) + len(closed)
