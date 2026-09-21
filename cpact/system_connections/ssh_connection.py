"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

===============================================================================
SSHConnection is an enhanced SSH utility class designed for robust remote command execution,
file transfers, and background task management in automated test environments. It extends
ConnectionInterface and integrates with Paramiko to support synchronous and asynchronous
operations with detailed logging and error handling.

Features:
- Establishes secure SSH connections using Paramiko.
- Supports synchronous and background command execution modes.
- Manages task lifecycle with tracking, termination, and result retrieval.
- Provides file upload and download capabilities via SFTP.
- Handles timeouts, termination signals, and partial output recovery.
- Thread-safe execution and task management using locks and queues.

Attributes:
    ssh_client (paramiko.SSHClient): Active SSH client instance.
    background_tasks (dict): Active background tasks indexed by task ID.
    completed_tasks (dict): Completed task results indexed by task ID.
    lock (threading.Lock): Lock for task management operations.
    connection_lock (threading.Lock): Lock for connection lifecycle operations.

Usage:
    Instantiate SSHConnection with a configuration dictionary.
    Use `connect()` to establish the connection.
    Call `execute_command()` to run commands and manage tasks.
    Use `disconnect()` to clean up resources and close the connection.
===============================================================================
"""

import time
import uuid
import queue
import paramiko
import traceback
import threading
from enum import Enum
from dataclasses import dataclass
from typing import Dict, Optional, Tuple, List, Any

import socket

from cpact.system_connections.base_connection import ConnectionInterface
from cpact.system_connections.constants import (
    ExecutionMode,
    TaskStatus,
    TaskResult,
    BackgroundTask,
)
from cpact.system_connections.connection_config import (
    ConnectionConfig,
    PRIVILEGE_NONE,
    PRIVILEGE_SUDO,
    PRIVILEGE_SU,
)
from cpact.system_connections.privilege import PrivilegedShell, PrivilegeEscalationError
from cpact.system_connections.retry import retry_call

# Exceptions that indicate a dropped/broken transport and warrant a reconnect.
_RECONNECT_EXCEPTIONS = (paramiko.SSHException, EOFError, socket.error, OSError)


class SSHConnection(ConnectionInterface):
    """Enhanced SSH connection with improved task management"""

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config=config)
        self.config = config
        # Strongly-typed view over the config; replaces the duplicated
        # _get_host/_get_username/... ladders (see connection_config.py).
        self.conn_config = ConnectionConfig.from_dict(config)
        self.ssh_client = None
        self.background_tasks: Dict[str, BackgroundTask] = {}
        self.completed_tasks: Dict[str, TaskResult] = {}
        self.lock = threading.Lock()
        self.connection_lock = threading.RLock()
        # Persistent elevated session state (see enable_privileged_mode()).
        self._priv_shell: Optional[PrivilegedShell] = None
        self._priv_mode: Optional[str] = None      # mode the shell was opened with
        self._priv_explicit = False                # True only via enable_privileged_mode()
        self._priv_lock = threading.Lock()
        # Guard against infinite reconnect recursion.
        self._reconnecting = False

    def connect(self) -> bool:
        """Establish SSH connection"""
        with self.connection_lock:
            try:
                if self.ssh_client:
                    self.disconnect()

                self.ssh_client = paramiko.SSHClient()
                self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

                host = self._get_host()
                port = self._get_ssh_port()
                username = self._get_username()
                password = self._get_password()

                self.logger.info(f"Connecting to {username}@{host}:{port}")

                retry = self.conn_config.retry

                def _do_connect():
                    self.ssh_client.connect(
                        hostname=host,
                        port=port,
                        username=username,
                        password=password,
                        timeout=30,
                        allow_agent=False,
                        look_for_keys=False,
                    )
                    return True

                retry_call(
                    _do_connect,
                    retries=retry.retry_count,
                    delay=retry.retry_delay,
                    exceptions=_RECONNECT_EXCEPTIONS,
                    logger=self.logger,
                    description=f"SSH connect to {host}:{port}",
                )

                self.logger.info("SSH connection established successfully")
                return True

            except Exception as e:
                tb_str = "".join(
                    traceback.format_exception(type(e), e, e.__traceback__)
                )
                self.logger.error(f"Formatted traceback:\n{tb_str}")
                self.logger.error(f"SSH connection failed: {e}")
                if self.ssh_client:
                    try:
                        self.ssh_client.close()
                    except:
                        pass
                    self.ssh_client = None
                return False

    def download_file(self, remote_path: str, local_path: str) -> bool:
        """Download file from remote server"""
        if not self.is_connected():
            if not self.connect():
                self.logger.error(
                    "Failed to establish SSH connection for file download"
                )
                return False

        try:
            sftp = self.ssh_client.open_sftp()
            sftp.get(remote_path, local_path)
            sftp.close()
            self.logger.info(
                f"File downloaded successfully: {remote_path} -> {local_path}"
            )
            return True
        except Exception as e:
            tb_str = "".join(traceback.format_exception(type(e), e, e.__traceback__))
            self.logger.error(f"Formatted traceback:\n{tb_str}")
            self.logger.error(f"Failed to download file: {e}")
            return False

    def upload_file(self, local_path: str, remote_path: str) -> bool:
        """Upload file to remote server"""
        if not self.is_connected():
            if not self.connect():
                self.logger.error("Failed to establish SSH connection for file upload")
                return False

        try:
            sftp = self.ssh_client.open_sftp()
            sftp.put(local_path, remote_path)
            sftp.close()
            self.logger.info(
                f"File uploaded successfully: {local_path} -> {remote_path}"
            )
            return True
        except Exception as e:
            tb_str = "".join(traceback.format_exception(type(e), e, e.__traceback__))
            self.logger.error(f"Formatted traceback:\n{tb_str}")
            self.logger.error(f"Failed to upload file: {e}")
            return False

    def execute_command(
        self,
        command: str,
        mode: ExecutionMode = ExecutionMode.SYNCHRONOUS,
        timeout: Optional[float] = None,
        wait: bool = False,
        use_sudo: bool = False,
        privilege_mode: Optional[str] = None,
    ) -> Optional[TaskResult]:
        """
        Execute SSH command based on the specified execution mode.

        Args:
            command: The command to execute
            mode: ExecutionMode enum (SYNCHRONOUS, BACKGROUND, BACKGROUND_WAIT)
            timeout: Timeout in seconds
            wait: If True with background mode, wait for completion after timeout
            use_sudo: Run the command through ``sudo -i`` with interactive
                password handling.
            privilege_mode: Explicit escalation mode ("sudo", "su" or "none").
                Overrides ``use_sudo`` and the config default when given.

        Returns:
            TaskResult for synchronous/background_wait execution,
            task_id for background execution when wait=False,
            None for background execution when wait=True but timeout exceeded

        Privileged routing precedence:
            1. A persistent elevated session (``enable_privileged_mode``) runs
               everything elevated.
            2. Otherwise, an explicit ``privilege_mode`` / ``use_sudo`` reuses a
               single elevated shell (escalated once, on first use) for this and
               all later privileged commands. It is torn down only at
               ``disconnect()`` — never per command.
            3. Otherwise, the normal non-interactive ``exec_command`` path runs.
        """
        if not self._ensure_connected():
            self.logger.error("Failed to establish SSH connection")
            return None

        effective_mode = self._resolve_privilege_mode(use_sudo, privilege_mode)

        # (1) An explicitly enabled persistent session runs everything elevated.
        with self._priv_lock:
            explicit_session = self._priv_explicit and self._priv_shell is not None
        if explicit_session and privilege_mode != PRIVILEGE_NONE:
            return self._execute_in_persistent_shell(command, timeout)

        # (2) A privileged command reuses one elevated shell (opened once). No
        #     per-command escalation, and no per-command teardown — the shell is
        #     closed only when the connection is disconnected.
        if effective_mode in (PRIVILEGE_SUDO, PRIVILEGE_SU):
            return self._execute_privileged_reused(command, effective_mode, timeout)

        # (3) Normal path.
        task_id = str(uuid.uuid4())

        if mode == ExecutionMode.SYNCHRONOUS:
            return self._execute_synchronous(task_id, command, timeout)

        elif mode == ExecutionMode.BACKGROUND:
            self._execute_background(task_id, command)
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
            self._execute_background(task_id, command)
            # Always wait for completion in this mode
            return self.wait_for_task(task_id, timeout)

    # ------------------------------------------------------------------ #
    # Reliability: reconnect + health check
    # ------------------------------------------------------------------ #
    def _ensure_connected(self) -> bool:
        """
        Ensure the transport is live, reconnecting once if it has dropped.

        Returns True if connected (or successfully reconnected).
        """
        if self.is_connected():
            return True
        if self._reconnecting:
            return False
        self._reconnecting = True
        try:
            self.logger.warning("SSH transport not active; attempting (re)connect")
            return self.connect()
        finally:
            self._reconnecting = False

    def health_check(self) -> bool:
        """
        Active liveness probe: round-trips ``echo health_check`` over the
        transport. Returns True only if the echo comes back intact.
        """
        if not self.is_connected():
            return False
        try:
            stdin, stdout, stderr = self.ssh_client.exec_command(
                "echo health_check", timeout=10
            )
            out = stdout.read().decode("utf-8", errors="ignore").strip()
            return out == "health_check"
        except Exception as e:
            self.logger.warning(f"Health check failed: {e}")
            return False

    # ------------------------------------------------------------------ #
    # Privilege escalation
    # ------------------------------------------------------------------ #
    def _resolve_privilege_mode(
        self, use_sudo: bool, privilege_mode: Optional[str]
    ) -> str:
        """Determine the effective escalation mode for a call."""
        if privilege_mode is not None:
            mode = privilege_mode.lower()
            return mode if mode in (PRIVILEGE_SUDO, PRIVILEGE_SU, PRIVILEGE_NONE) else PRIVILEGE_NONE
        if use_sudo:
            return PRIVILEGE_SUDO
        # Fall back to the configured default (may be "none").
        return self.conn_config.privilege_mode

    def _open_privileged_shell(self, mode: str) -> PrivilegedShell:
        """Open an interactive PTY shell and escalate it to root."""
        transport = self.ssh_client.get_transport()
        if transport is None or not transport.is_active():
            raise PrivilegeEscalationError("SSH transport is not active")

        channel = transport.open_session()
        channel.get_pty()
        channel.invoke_shell()

        password = self.conn_config.privilege_password(mode)
        source = self.conn_config.privilege_password_source(mode)
        self.logger.info(
            f"Opening privileged shell (mode={mode}, password source={source})"
        )
        if source == "login-fallback":
            self.logger.info(
                "No dedicated %s password configured; using the SSH login "
                "password. If your sudo/su password differs, set "
                "'%s_%s_password' (or a bare '%s_password') in the config.",
                mode, (self.conn_config.prefix or "<section>"), mode, mode,
            )
        shell = PrivilegedShell(channel, password, self.logger)
        try:
            shell.escalate(mode)
        except Exception:
            # Escalation failed (e.g. wrong sudo password). Force this
            # interactive channel closed immediately — a leaked half-open
            # channel is exactly what makes the transport close hang later.
            try:
                shell.close()
            except Exception:
                pass
            raise
        return shell

    def _get_or_open_privileged_shell(self, mode: str) -> PrivilegedShell:
        """
        Return the connection's single elevated shell, opening and escalating it
        on first use. Reused across commands; if a different mode is requested
        the previous shell is closed and a new one opened.
        """
        with self._priv_lock:
            if self._priv_shell is not None and self._priv_mode == mode:
                return self._priv_shell
            if self._priv_shell is not None:
                # Mode changed — replace the shell.
                try:
                    self._priv_shell.close()
                except Exception:
                    pass
                self._priv_shell = None
                self._priv_mode = None
            shell = self._open_privileged_shell(mode)  # may raise; nothing stored
            self._priv_shell = shell
            self._priv_mode = mode
            return shell

    def _execute_privileged_reused(
        self, command: str, mode: str, timeout: Optional[float]
    ) -> TaskResult:
        """Run a command in the reused elevated shell. Never closes the shell."""
        task_id = str(uuid.uuid4())
        start_time = time.time()
        result = TaskResult(
            task_id=task_id,
            command=command,
            status=TaskStatus.RUNNING,
            start_time=start_time,
        )
        try:
            shell = self._get_or_open_privileged_shell(mode)
            stdout, exit_code = shell.run(command, timeout=timeout)
            result.stdout = stdout
            result.return_code = exit_code
            result.status = TaskStatus.COMPLETED if exit_code == 0 else TaskStatus.FAILED
        except PrivilegeEscalationError as e:
            self.logger.error(f"Privilege escalation failed: {e}")
            result.status = TaskStatus.FAILED
            result.stderr = str(e)
            result.return_code = -1
        except Exception as e:
            self.logger.error(f"Privileged command error: {e}")
            result.status = TaskStatus.FAILED
            result.stderr = str(e)
            result.return_code = -1
        result.end_time = time.time()
        result.execution_time = result.end_time - result.start_time
        return result

    def _execute_privileged_oneshot(
        self, command: str, mode: str, timeout: Optional[float]
    ) -> TaskResult:
        """Escalate, run one command, tear the elevated shell down, return result."""
        task_id = str(uuid.uuid4())
        start_time = time.time()
        result = TaskResult(
            task_id=task_id,
            command=command,
            status=TaskStatus.RUNNING,
            start_time=start_time,
        )
        shell = None
        try:
            self.logger.info(f"Executing privileged ({mode}) command")
            shell = self._open_privileged_shell(mode)
            stdout, exit_code = shell.run(command, timeout=timeout)
            result.stdout = stdout
            result.return_code = exit_code
            result.status = TaskStatus.COMPLETED if exit_code == 0 else TaskStatus.FAILED
        except PrivilegeEscalationError as e:
            self.logger.error(f"Privilege escalation failed: {e}")
            result.status = TaskStatus.FAILED
            result.stderr = str(e)
            result.return_code = -1
        except Exception as e:
            self.logger.error(f"Privileged command error: {e}")
            result.status = TaskStatus.FAILED
            result.stderr = str(e)
            result.return_code = -1
        finally:
            if shell is not None:
                shell.close()

        result.end_time = time.time()
        result.execution_time = result.end_time - result.start_time
        return result

    def _execute_in_persistent_shell(
        self, command: str, timeout: Optional[float]
    ) -> TaskResult:
        """Run a command inside the already-elevated persistent shell."""
        task_id = str(uuid.uuid4())
        start_time = time.time()
        result = TaskResult(
            task_id=task_id,
            command=command,
            status=TaskStatus.RUNNING,
            start_time=start_time,
        )
        try:
            with self._priv_lock:
                shell = self._priv_shell
                if shell is None:
                    raise PrivilegeEscalationError("no active privileged session")
                stdout, exit_code = shell.run(command, timeout=timeout)
            result.stdout = stdout
            result.return_code = exit_code
            result.status = TaskStatus.COMPLETED if exit_code == 0 else TaskStatus.FAILED
        except Exception as e:
            self.logger.error(f"Privileged session command error: {e}")
            result.status = TaskStatus.FAILED
            result.stderr = str(e)
            result.return_code = -1

        result.end_time = time.time()
        result.execution_time = result.end_time - result.start_time
        return result

    def enable_privileged_mode(self, mode: Optional[str] = None) -> bool:
        """
        Open a persistent elevated shell so subsequent ``execute_command`` calls
        run as root without re-authenticating.

        Args:
            mode: "sudo" or "su". Defaults to the configured ``privilege_mode``,
                  or "sudo" if none is configured.
        """
        if not self._ensure_connected():
            self.logger.error("Cannot enable privileged mode: not connected")
            return False

        mode = (mode or self.conn_config.privilege_mode or PRIVILEGE_SUDO).lower()
        if mode not in (PRIVILEGE_SUDO, PRIVILEGE_SU):
            mode = PRIVILEGE_SUDO

        with self._priv_lock:
            if self._priv_shell is not None:
                self.logger.info("Privileged mode already enabled")
                return True
            try:
                self._priv_shell = self._open_privileged_shell(mode)
                self._priv_mode = mode
                self._priv_explicit = True
                self.logger.info(f"Persistent privileged mode enabled ({mode})")
                return True
            except Exception as e:
                self.logger.error(f"Failed to enable privileged mode: {e}")
                self._priv_shell = None
                self._priv_mode = None
                return False

    def disable_privileged_mode(self) -> None:
        """Close the persistent/reused elevated shell, if any."""
        with self._priv_lock:
            if self._priv_shell is not None:
                self.logger.info("Disabling persistent privileged mode")
                try:
                    self._priv_shell.close()
                except Exception:
                    pass
                self._priv_shell = None
            self._priv_mode = None
            self._priv_explicit = False

    def _execute_synchronous(
        self, task_id: str, command: str, timeout: Optional[float] = None
    ) -> TaskResult:
        """Execute command synchronously and return result immediately.

        If the exec channel/transport is torn down as the command runs
        (``SSHException: Channel closed``, EOF, or a socket error — common when a
        tunnel drops between steps, or a manager/BMC sshd closes extra sessions),
        force one clean reconnect and retry the command a single time. A read
        *timeout* is not a transport failure, so it maps to TIMEOUT without a
        reconnect.
        """
        start_time = time.time()
        result = TaskResult(
            task_id=task_id,
            command=command,
            status=TaskStatus.RUNNING,
            start_time=start_time,
        )

        attempts = 2  # initial try + one reconnect-and-retry
        for attempt in range(attempts):
            try:
                self.logger.info(f"Executing synchronous command: {command}")
                stdin, stdout, stderr = self.ssh_client.exec_command(
                    command, timeout=timeout
                )
                if timeout:
                    stdout.channel.settimeout(timeout)
                    stderr.channel.settimeout(timeout)

                stdout_data = stdout.read().decode("utf-8", errors="ignore")
                stderr_data = stderr.read().decode("utf-8", errors="ignore")
                exit_code = stdout.channel.recv_exit_status()

                result.return_code = exit_code
                result.stdout = stdout_data
                result.stderr = stderr_data
                result.status = (
                    TaskStatus.COMPLETED if exit_code == 0 else TaskStatus.FAILED
                )
                break  # success

            except socket.timeout:
                # Read/exec exceeded the timeout — not a transport failure.
                result.status = TaskStatus.TIMEOUT
                result.stderr = f"Command timeout after {timeout} seconds"
                result.return_code = -1
                break

            except _RECONNECT_EXCEPTIONS as e:
                # Transport/channel died (e.g. 'Channel closed'). is_connected()
                # may still report active, so force a full reconnect and retry.
                self.logger.warning(
                    f"SSH channel/transport error during exec ('{e}')."
                )
                if attempt < attempts - 1 and self._force_reconnect():
                    self.logger.info("Reconnected; retrying command once.")
                    continue
                result.status = TaskStatus.FAILED
                result.stderr = str(e)
                result.return_code = -1
                break

            except Exception as e:
                tb_str = "".join(
                    traceback.format_exception(type(e), e, e.__traceback__)
                )
                self.logger.error(f"Formatted traceback:\n{tb_str}")
                self.logger.error(f"Error executing synchronous command: {e}")
                result.status = TaskStatus.FAILED
                result.stderr = str(e)
                result.return_code = -1
                break

        result.end_time = time.time()
        result.execution_time = result.end_time - result.start_time

        self.logger.info(f"Synchronous command completed with status: {result.status}")
        return result

    def _force_reconnect(self) -> bool:
        """Tear down and re-establish the connection once.

        Used to recover from a dropped transport/channel mid-command. For a
        tunnelled connection ``connect()`` also rebuilds the tunnels, so a dead
        tunnel is re-established too. Returns True if reconnected.
        """
        if getattr(self, "_reconnecting", False):
            return False
        self._reconnecting = True
        try:
            try:
                self.disconnect()
            except Exception:
                pass
            try:
                return bool(self.connect())
            except Exception as e:
                self.logger.error(f"Reconnect failed: {e}")
                return False
        finally:
            self._reconnecting = False

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
            # Execute command
            stdin, stdout, stderr = self.ssh_client.exec_command(command)

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
            except:
                pass

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

    def disconnect(self) -> None:
        """Close SSH connection and cleanup"""
        self.logger.info("Disconnecting SSH connection...")

        # Close any persistent elevated shell first.
        self.disable_privileged_mode()

        # Terminate all running tasks
        terminated = self.terminate_all_tasks()
        if terminated:
            self.logger.info(f"Terminated {len(terminated)} running tasks")
            # Wait briefly for terminated tasks to clean up. Only pay this cost
            # when there was actually something to terminate (previously this
            # 1s sleep ran on every disconnect, tunnels included).
            time.sleep(1)

        # Close SSH connection
        with self.connection_lock:
            if self.ssh_client:
                client = self.ssh_client
                # paramiko's close() can block indefinitely when an interactive
                # channel is left half-open. Run it under a watchdog so a stuck
                # close can never hang the caller; if it overruns we abandon the
                # (daemon) thread and drop our reference — the transport socket
                # is torn down by the OS when the process exits.
                closed = self._close_client_bounded(client, timeout=5.0)
                if closed:
                    self.logger.info("SSH connection closed")
                else:
                    self.logger.warning(
                        "SSH close did not complete within 5s; abandoning the "
                        "connection to avoid a hang"
                    )
                self.ssh_client = None

    def _close_client_bounded(self, client, timeout: float) -> bool:
        """Call client.close() but never block longer than ``timeout`` seconds."""
        error: List[BaseException] = []

        def _closer() -> None:
            try:
                # Proactively force any lingering channels down first; this is
                # what usually unblocks a stuck transport close.
                transport = client.get_transport()
                if transport is not None:
                    for chan in list(getattr(transport, "_channels", {}).values()):
                        try:
                            chan.close()
                        except Exception:
                            pass
                client.close()
            except BaseException as e:  # noqa: BLE001 - reported via `error`
                error.append(e)

        t = threading.Thread(target=_closer, name="ssh-close-watchdog", daemon=True)
        t.start()
        t.join(timeout)
        if t.is_alive():
            return False
        if error:
            tb_str = "".join(
                traceback.format_exception(
                    type(error[0]), error[0], error[0].__traceback__
                )
            )
            self.logger.error(f"Formatted traceback:\n{tb_str}")
            self.logger.warning(f"Error closing SSH connection: {error[0]}")
        return True

    def is_connected(self) -> bool:
        """Check if SSH connection is active"""
        with self.connection_lock:
            return (
                self.ssh_client is not None
                and self.ssh_client.get_transport() is not None
                and self.ssh_client.get_transport().is_active()
            )

    # Additional compatibility methods for the original SSH interface
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

        self.close_task(actual_task_id)

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

    # Disconnect wrapper for compatibility
    def close_connection(self) -> None:
        """Close SSH connection and cleanup all tasks (compatibility method)"""
        self.disconnect()

    # Configuration helper methods.
    #
    # These now delegate to the centralized ConnectionConfig so host / port /
    # username / password resolution lives in exactly one place. The method
    # names are preserved because TunnelConnection overrides _get_host and
    # _get_ssh_port to redirect to the local tunnel endpoint.
    def _get_host(self) -> str:
        """Extract host based on connection type"""
        return self.conn_config.host

    def _get_ssh_port(self) -> int:
        """Get SSH port from config"""
        return self.conn_config.ssh_port

    def _get_username(self) -> str:
        """Get username from config"""
        return self.conn_config.username

    def _get_password(self) -> str:
        """Get password from config"""
        return self.conn_config.password
