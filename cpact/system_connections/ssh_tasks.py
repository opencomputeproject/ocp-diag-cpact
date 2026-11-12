"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.
This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

===============================================================================
Background-task management for SSHConnection.

SSHBackgroundTaskMixin holds the lifecycle of commands started with
ExecutionMode.BACKGROUND / BACKGROUND_WAIT: starting them (plain or in a
dedicated privileged shell), waiting for and querying results, terminating
them (including killing the remote process group) and cleaning up. It relies
on attributes set up by SSHConnection.__init__ (ssh_client, lock, logger,
conn_config, background_tasks, completed_tasks, _posix_shell) and on
SSHConnection._open_privileged_shell().

Extracted from ssh_connection.py; behaviour is unchanged.
===============================================================================
"""

import math
import queue
import re
import threading
import time
import traceback
import uuid
from typing import Any, Dict, List, Optional, Tuple

from cpact.system_connections.connection_config import parse_optional_bool
from cpact.system_connections.constants import (
    BackgroundTask,
    ExecutionMode,
    TaskResult,
    TaskStatus,
)

# First stdout line of a tracked SSH command (synchronous or background): the
# remote shell's PID. sshd starts non-PTY commands in a new session, so this
# PID is also the process group id of everything the command spawns.
_PID_MARKER = "__CPACT_REMOTE_PID__="


def _extract_pid_marker(data: str) -> Tuple[str, Optional[int], bool]:
    """Strip the PID marker line from the start of ``data``.

    Returns ``(remaining_data, pid, done)``; ``done`` is False while the
    marker line may still be incomplete.
    """
    if not data.startswith(_PID_MARKER):
        if _PID_MARKER.startswith(data):
            return data, None, False
        return data, None, True
    if "\n" not in data:
        return data, None, False
    line, rest = data.split("\n", 1)
    value = line[len(_PID_MARKER):].strip()
    return rest, (int(value) if value.isdigit() else None), True


class SSHBackgroundTaskMixin:
    """Background task lifecycle for SSHConnection (see module docstring)."""

    def _start_privileged_background(
        self,
        command: str,
        priv_mode: str,
        exec_mode: ExecutionMode,
        wait: bool,
        timeout: Optional[float],
    ) -> TaskResult:
        """
        Run a privileged command as a tracked background task.

        Each task gets its own escalated PTY shell, so it neither blocks nor
        interleaves with the shared shell used by synchronous privileged steps,
        and terminating it (Ctrl+C + closing the PTY) stops the remote command.
        """
        task_id = str(uuid.uuid4())
        thread = threading.Thread(
            target=self._privileged_background_worker,
            args=(task_id, command, priv_mode),
            daemon=True,
        )
        background_task = BackgroundTask(task_id, command, self.ssh_client, thread)
        with self.lock:
            self.background_tasks[task_id] = background_task
        self.logger.info(f"Starting privileged ({priv_mode}) background task {task_id}")
        thread.start()

        if exec_mode == ExecutionMode.BACKGROUND_WAIT or (wait and timeout is not None):
            return self.wait_for_task(task_id, timeout)
        return TaskResult(
            task_id=task_id,
            command=command,
            status=TaskStatus.RUNNING,
            start_time=background_task.start_time,
        )

    def _privileged_background_worker(self, task_id: str, command: str, priv_mode: str) -> None:
        """Worker for _start_privileged_background(); mirrors _background_worker()."""
        start_time = time.time()
        shell = None
        try:
            shell = self._open_privileged_shell(priv_mode)
            with self.lock:
                background_task = self.background_tasks.get(task_id)
                if background_task is not None:
                    background_task.priv_shell = shell
                already_terminated = background_task is None or background_task.terminated
            if already_terminated:
                stdout, exit_code = "", -1
            else:
                # No client-side limit: wait_for_task()/terminate_task() bound it.
                stdout, exit_code = shell.run(command, timeout=math.inf)
            with self.lock:
                terminated = (
                    task_id in self.background_tasks
                    and self.background_tasks[task_id].terminated
                )
            if terminated:
                status = TaskStatus.TERMINATED
            else:
                status = TaskStatus.COMPLETED if exit_code == 0 else TaskStatus.FAILED
            result = TaskResult(
                task_id=task_id,
                command=command,
                status=status,
                return_code=exit_code,
                stdout=stdout,
                start_time=start_time,
                end_time=time.time(),
            )
        except Exception as e:
            self.logger.error(f"Privileged background task {task_id} failed: {e}")
            result = TaskResult(
                task_id=task_id,
                command=command,
                status=TaskStatus.FAILED,
                return_code=-1,
                stderr=str(e),
                start_time=start_time,
                end_time=time.time(),
            )
        finally:
            if shell is not None:
                shell.close()
        result.execution_time = result.end_time - result.start_time

        with self.lock:
            if task_id in self.background_tasks:
                background_task = self.background_tasks[task_id]
                background_task.result_queue.put(result)
                background_task.completed.set()
                del self.background_tasks[task_id]
                self.completed_tasks[task_id] = result
        self.logger.info(
            f"Privileged background task {task_id} completed with status: {result.status}"
        )

    def _execute_background(self, task_id: str, command: str) -> None:
        """Execute command in background thread."""
        try:
            self.logger.info(f"Starting background task {task_id}: {command}")

            thread = threading.Thread(
                target=self._background_worker, args=(task_id, command), daemon=True
            )

            background_task = BackgroundTask(task_id, command, self.ssh_client, thread)

            with self.lock:
                self.background_tasks[task_id] = background_task

            thread.start()
            self.logger.info(f"Started background task {task_id}")

        except Exception as e:
            tb_str = "".join(traceback.format_exception(type(e), e, e.__traceback__))
            self.logger.error(f"Formatted traceback:\n{tb_str}")
            self.logger.error(f"Failed to start background task {task_id}: {e}")
            result = TaskResult(
                task_id=task_id,
                command=command,
                status=TaskStatus.FAILED,
                stderr=str(e),
                return_code=-1,
                start_time=time.time(),
            )
            with self.lock:
                self.completed_tasks[task_id] = result

    def _background_worker(self, task_id: str, command: str) -> TaskResult:
        """Worker function for background task execution."""
        start_time = time.time()
        stdout_data = ""
        stderr_data = ""
        stdin = stdout = stderr = None

        try:
            track_pid = self._track_remote_pid()
            remote_command = (
                f'echo "{_PID_MARKER}$$"; {command}' if track_pid else command
            )
            pid_pending = track_pid

            # Execute command
            stdin, stdout, stderr = self.ssh_client.exec_command(remote_command)

            # Store channels in background task for potential termination
            with self.lock:
                if task_id in self.background_tasks:
                    self.background_tasks[task_id].channels = (stdin, stdout, stderr)

            # Read output with streaming capability
            stdout_data = ""
            stderr_data = ""

            # Set non-blocking mode and timeouts
            stdout.channel.settimeout(1.0)
            stderr.channel.settimeout(1.0)

            while True:
                # Check if task was terminated
                with self.lock:
                    if (
                        task_id in self.background_tasks
                        and self.background_tasks[task_id].terminated
                    ):
                        self.logger.info(f"Background task {task_id} was terminated")
                        break

                try:
                    # Read available stdout
                    if stdout.channel.recv_ready():
                        chunk = stdout.channel.recv(4096).decode(
                            "utf-8", errors="ignore"
                        )
                        stdout_data += chunk
                        if pid_pending:
                            stdout_data, pid, done = _extract_pid_marker(stdout_data)
                            if done:
                                pid_pending = False
                                if pid is not None:
                                    with self.lock:
                                        if task_id in self.background_tasks:
                                            self.background_tasks[task_id].remote_pid = pid

                    # Read available stderr
                    if stderr.channel.recv_stderr_ready():
                        chunk = stderr.channel.recv_stderr(4096).decode(
                            "utf-8", errors="ignore"
                        )
                        stderr_data += chunk

                    # Check if command finished
                    if stdout.channel.exit_status_ready():
                        # Read any remaining data
                        while stdout.channel.recv_ready():
                            chunk = stdout.channel.recv(4096).decode(
                                "utf-8", errors="ignore"
                            )
                            stdout_data += chunk
                        while stderr.channel.recv_stderr_ready():
                            chunk = stderr.channel.recv_stderr(4096).decode(
                                "utf-8", errors="ignore"
                            )
                            stderr_data += chunk
                        break

                    time.sleep(0.1)

                except Exception as e:
                    tb_str = "".join(
                        traceback.format_exception(type(e), e, e.__traceback__)
                    )
                    self.logger.error(f"Formatted traceback:\n{tb_str}")
                    # Check if it's a timeout (normal) or real error
                    if "timeout" not in str(e).lower():
                        self.logger.warning(f"Error reading from channels: {e}")
                        break

            # Get exit code
            exit_code = -1
            if pid_pending:
                stdout_data, _, _ = _extract_pid_marker(stdout_data)
            try:
                with self.lock:
                    if (
                        task_id in self.background_tasks
                        and not self.background_tasks[task_id].terminated
                    ):
                        exit_code = stdout.channel.recv_exit_status()
            except Exception as e:
                tb_str = "".join(
                    traceback.format_exception(type(e), e, e.__traceback__)
                )
                self.logger.error(f"Formatted traceback:\n{tb_str}")
                self.logger.warning(f"Could not get exit status: {e}")

            # Determine final status
            with self.lock:
                is_terminated = (
                    task_id in self.background_tasks
                    and self.background_tasks[task_id].terminated
                )

            if is_terminated:
                status = TaskStatus.TERMINATED
            else:
                status = TaskStatus.COMPLETED if exit_code == 0 else TaskStatus.FAILED

            result = TaskResult(
                task_id=task_id,
                command=command,
                status=status,
                return_code=exit_code,
                stdout=stdout_data,
                stderr=stderr_data,
                start_time=start_time,
                end_time=time.time(),
            )
            result.execution_time = result.end_time - result.start_time

        except Exception as e:
            tb_str = "".join(traceback.format_exception(type(e), e, e.__traceback__))
            self.logger.error(f"Formatted traceback:\n{tb_str}")
            self.logger.error(f"Error in background worker for task {task_id}: {e}")
            result = TaskResult(
                task_id=task_id,
                command=command,
                status=TaskStatus.FAILED,
                return_code=-1,
                stdout=stdout_data,  # Return any partial stdout we collected
                stderr=stderr_data
                + f"\nError: {str(e)}",  # Include partial stderr + error
                start_time=start_time,
                end_time=time.time(),
            )
            result.execution_time = result.end_time - result.start_time

        finally:
            # Always close channels to prevent resource leaks
            try:
                if stdin:
                    stdin.close()
                if stdout:
                    stdout.close()
                if stderr:
                    stderr.close()
            except Exception as e:
                self.logger.debug(f"Error closing channels for task {task_id}: {e}")

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
        return result

    def wait_for_task(
        self, task_id: str, timeout: Optional[float] = None
    ) -> Optional[TaskResult]:
        """
        Wait for a specific background task to complete.

        Args:
            task_id: ID of the task to wait for (ensure it's a string)
            timeout: Maximum time to wait in seconds

        Returns:
            TaskResult if task completes, None if timeout or task not found
        """
        try:
            # Ensure task_id is a string, not a TaskResult object
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

            # Timeout occurred - terminate task and return partial results
            self.logger.warning(
                f"Timeout waiting for task {actual_task_id}, terminating and collecting results"
            )

            # Force terminate the task
            self.terminate_task(actual_task_id)

            # Wait a bit for termination to complete
            background_task.completed.wait(timeout=2.0)

            # Try to get the result from the queue or completed tasks
            try:
                return background_task.result_queue.get_nowait()
            except queue.Empty:
                with self.lock:
                    if actual_task_id in self.completed_tasks:
                        return self.completed_tasks[actual_task_id]

                    result = TaskResult(
                        task_id=actual_task_id,
                        command=background_task.command,
                        status=TaskStatus.TIMEOUT,
                        return_code=-1,
                        stdout="",
                        stderr=f"Task timed out after {timeout} seconds",
                        start_time=background_task.start_time,
                        end_time=time.time(),
                    )
                    result.execution_time = result.end_time - result.start_time

                    self.completed_tasks[actual_task_id] = result
                    return result

        except Exception as e:
            tb_str = "".join(traceback.format_exception(type(e), e, e.__traceback__))
            self.logger.error(f"Formatted traceback:\n{tb_str}")
            self.logger.error(f"Error waiting for task {task_id}: {e}")
            # Even on error, try to return something useful
            actual_task_id = (
                str(task_id) if not hasattr(task_id, "task_id") else task_id.task_id
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
            task_id: ID of the task (ensure it's a string)

        Returns:
            Dictionary with task details and result, or None if not found
        """
        # Ensure task_id is a string, not a TaskResult object
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
    ) -> Optional[Tuple[str, str, int, str]]:
        """
        Wait for a specific background task and get detailed result.

        Args:
            task_id: ID of the task to wait for
            timeout: Maximum time to wait in seconds
            wait: If True, wait for completion; if False, return current status

        Returns:
            Tuple of (stdout, stderr, exit_code, status) - always returns a result, never None for timeouts
        """
        # Ensure task_id is a string, not a TaskResult object
        if hasattr(task_id, "task_id"):
            actual_task_id = task_id.task_id
        else:
            actual_task_id = str(task_id)

        if not wait:
            details = self.get_task_result_and_details(actual_task_id)
            if details:
                return (
                    details.get("stdout", ""),
                    details.get("stderr", ""),
                    details.get("return_code", -1),
                    details.get("status", "unknown"),
                )
            # Return empty result instead of None
            return ("", f"Task {actual_task_id} not found", -1, "not_found")

        # Wait for task completion
        result = self.wait_for_task(actual_task_id, timeout)

        # wait_for_task now always returns a result (even for timeouts), so this should not be None
        if result is None:
            # This should rarely happen now, but handle it just in case
            self.logger.warning(f"Unexpected None result for task {actual_task_id}")
            return ("", f"Task {actual_task_id} returned None result", -1, "error")

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
            tb_str = "".join(traceback.format_exception(type(e), e, e.__traceback__))
            self.logger.error(f"Formatted traceback:\n{tb_str}")
            self.logger.error(f"Error getting all tasks: {e}")

        return all_tasks

    def _track_remote_pid(self) -> bool:
        """
        Whether commands get the PID-marker prefix.

        ``<prefix>_track_remote_pid`` wins when set; otherwise a one-time probe
        checks for a POSIX shell, so vendor CLIs (e.g. a RackManager shell) are
        never wrapped.
        """
        try:
            value = parse_optional_bool(self.conn_config.track_remote_pid)
        except ValueError:
            self.logger.warning(
                f"Invalid track_remote_pid value {self.conn_config.track_remote_pid!r}; auto-detecting"
            )
            value = None
        if value is not None:
            return value
        return self._remote_shell_is_posix()

    def _remote_shell_is_posix(self) -> bool:
        """Probe (once per connection) whether the remote shell is POSIX sh compatible."""
        if self._posix_shell is not None:
            return self._posix_shell
        # Arithmetic expansion plus $$ (a numeric PID) is POSIX-specific: cmd.exe
        # prints it literally and PowerShell does not produce a PID for $$.
        probe = 'echo "__cpact_probe_$((6*7))_$$"'
        is_posix = False
        try:
            _, stdout, _ = self.ssh_client.exec_command(probe, timeout=15)
            out = stdout.read().decode("utf-8", errors="ignore").strip()
            is_posix = re.fullmatch(r"__cpact_probe_42_\d+", out) is not None
        except Exception as e:
            self.logger.warning(f"POSIX shell probe failed ({e}); not wrapping commands")
        self._posix_shell = is_posix
        self.logger.info(
            f"Remote shell is {'POSIX' if is_posix else 'not POSIX'}; remote PID "
            f"tracking {'enabled' if is_posix else 'disabled'} for timeout/terminate"
        )
        return is_posix

    def _kill_remote_process_group(self, pid: int) -> None:
        """Best-effort TERM, then KILL, of a remote background task's process group.

        Closing a non-PTY channel does not stop the remote command, so without
        this a timed-out or terminated task keeps running on the target.
        """
        pid = int(pid)
        # `kill -SIG -PGID` (no `--`): dash/BusyBox kill builtins reject `--`.
        kill_cmd = (
            f"kill -TERM -{pid} 2>/dev/null || kill -TERM {pid} 2>/dev/null; "
            f"sleep 2; "
            f"kill -0 -{pid} 2>/dev/null && kill -KILL -{pid} 2>/dev/null; "
            f"kill -0 {pid} 2>/dev/null && kill -KILL {pid} 2>/dev/null; true"
        )
        try:
            _, stdout, _ = self.ssh_client.exec_command(kill_cmd, timeout=15)
            stdout.channel.recv_exit_status()
            self.logger.info(f"Killed remote process group {pid}")
        except Exception as e:
            self.logger.warning(f"Could not kill remote process group {pid}: {e}")

    def terminate_task(self, task_id: str) -> bool:
        """
        Terminate a running background task.

        Args:
            task_id: ID of the task to terminate (ensure it's a string)

        Returns:
            True if task was terminated, False if not found or already completed
        """
        # Ensure task_id is a string, not a TaskResult object
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

            # Mark as terminated - the background worker will detect this
            background_task.terminated = True

        try:
            if background_task.remote_pid:
                self._kill_remote_process_group(background_task.remote_pid)

            if background_task.priv_shell is not None:
                # Privileged task: Ctrl+C the PTY, then close it (SIGHUP).
                try:
                    background_task.priv_shell.interrupt(resync_timeout=2.0)
                finally:
                    background_task.priv_shell.close()

            # Try to send Ctrl+C signal to the command if channels are available
            if background_task.channels:
                try:
                    stdin, stdout, stderr = background_task.channels
                    if stdout.channel and not stdout.channel.closed:
                        stdout.channel.send("\x03")  # Send Ctrl+C
                        time.sleep(0.1)
                    if stdout.channel and not stdout.channel.closed:
                        stdout.channel.close()
                except Exception as e:
                    tb_str = "".join(
                        traceback.format_exception(type(e), e, e.__traceback__)
                    )
                    self.logger.error(f"Formatted traceback:\n{tb_str}")
                    self.logger.warning(f"Could not send termination signal: {e}")

            self.logger.info(f"Initiated termination for task {actual_task_id}")
            return True

        except Exception as e:
            tb_str = "".join(traceback.format_exception(type(e), e, e.__traceback__))
            self.logger.error(f"Formatted traceback:\n{tb_str}")
            self.logger.error(f"Failed to terminate task {actual_task_id}: {e}")

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
                tb_str = "".join(
                    traceback.format_exception(
                        type(cleanup_error), cleanup_error, cleanup_error.__traceback__
                    )
                )
                self.logger.error(f"Formatted traceback:\n{tb_str}")
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
        with self.lock:
            return self.completed_tasks.get(task_id)

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

    def get_task_result(
        self,
        task_id: str,
        wait: bool = False,
        timeout: float = None,
        force_stop: bool = False,
    ) -> Optional[Tuple[str, str, int, str]]:
        """
        Get results from background task (compatibility method)

        Args:
            task_id: Task identifier
            wait: If True, wait for task completion
            timeout: Maximum time to wait
            force_stop: If True, terminate running task

        Returns:
            Tuple of (stdout, stderr, exit_code, status) or None if not ready
        """
        # Ensure task_id is a string
        if hasattr(task_id, "task_id"):
            actual_task_id = task_id.task_id
        else:
            actual_task_id = str(task_id)

        if force_stop:
            self.terminate_task(actual_task_id)

        return self.wait_for_task_with_details(actual_task_id, timeout, wait)

    def get_all_background_results(
        self,
        wait: bool = True,
        timeout: float = None,
        force_stop_remaining: bool = True,
    ) -> Dict[str, Tuple[str, str, int, str]]:
        """
        Get results from all background tasks (compatibility method)

        Args:
            wait: If True, wait for tasks to complete
            timeout: Maximum time to wait for each task (None = no timeout)
            force_stop_remaining: If True, force stop tasks that don't complete within timeout

        Returns:
            Dict mapping task_id to (stdout, stderr, exit_code, status)
        """
        results = {}

        if wait:
            all_results = self.wait_for_all_tasks(timeout)
            for task_id, result in all_results.items():
                results[task_id] = (
                    result.stdout,
                    result.stderr,
                    result.return_code,
                    result.status.value,
                )
        else:
            # Just get current status of all tasks
            all_tasks = self.get_all_tasks()
            for task_id, details in all_tasks.items():
                results[task_id] = (
                    details.get("stdout", ""),
                    details.get("stderr", ""),
                    details.get("return_code", -1),
                    details.get("status", "unknown"),
                )

        if force_stop_remaining:
            running_tasks = [
                tid for tid, (_, _, _, status) in results.items() if status == "running"
            ]
            for task_id in running_tasks:
                self.terminate_task(task_id)

        return results

    def cleanup_task(self, task_id: str) -> bool:
        """Clean up task resources (compatibility method)"""
        # Ensure task_id is a string
        if hasattr(task_id, "task_id"):
            actual_task_id = task_id.task_id
        else:
            actual_task_id = str(task_id)

        return self.close_task(actual_task_id)

    def cleanup_completed_tasks(self) -> int:
        """Clean up all completed tasks (compatibility method)"""
        return len(self.close_all_completed_tasks())

    def cleanup_all_tasks(self) -> int:
        """Clean up all tasks (completed and running) (compatibility method)"""
        # First terminate any running tasks
        terminated = self.terminate_all_tasks()

        # Clean up all tasks
        closed = self.close_all_completed_tasks()

        return len(terminated) + len(closed)
