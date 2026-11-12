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
import paramiko
import traceback
import threading
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
from cpact.system_connections.ssh_client import create_ssh_client, HOST_KEY_ERRORS
from cpact.system_connections.ssh_tasks import (
    _PID_MARKER,
    SSHBackgroundTaskMixin,
)

# Exceptions that indicate a dropped/broken transport and warrant a reconnect.
_RECONNECT_EXCEPTIONS = (paramiko.SSHException, EOFError, socket.error, OSError)


class SSHConnection(SSHBackgroundTaskMixin, ConnectionInterface):
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
        # Cached result of the POSIX-shell probe (None = not probed yet).
        self._posix_shell: Optional[bool] = None

    def connect(self) -> bool:
        """Establish SSH connection"""
        with self.connection_lock:
            try:
                if self.ssh_client:
                    self.disconnect()
                self._posix_shell = None

                self.ssh_client = create_ssh_client(
                    self.conn_config.known_hosts_file or None
                )

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
                    give_up_on=HOST_KEY_ERRORS,
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
                    except Exception:
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
        is_background = mode in (ExecutionMode.BACKGROUND, ExecutionMode.BACKGROUND_WAIT)

        # (1) An explicitly enabled persistent session runs everything elevated.
        with self._priv_lock:
            explicit_session = self._priv_explicit and self._priv_shell is not None
            session_mode = self._priv_mode
        if explicit_session and privilege_mode != PRIVILEGE_NONE:
            if is_background:
                return self._start_privileged_background(
                    command, session_mode or effective_mode, mode, wait, timeout
                )
            return self._execute_in_persistent_shell(command, timeout)

        # (2) A privileged command reuses one elevated shell (opened once). No
        #     per-command escalation, and no per-command teardown — the shell is
        #     closed only when the connection is disconnected. Background
        #     privileged commands get their own elevated shell (see below).
        if effective_mode in (PRIVILEGE_SUDO, PRIVILEGE_SU):
            if is_background:
                return self._start_privileged_background(
                    command, effective_mode, mode, wait, timeout
                )
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
            self._apply_privileged_result(result, stdout, exit_code, timeout)
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
            self._apply_privileged_result(result, stdout, exit_code, timeout)
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
            self._apply_privileged_result(result, stdout, exit_code, timeout)
        except Exception as e:
            self.logger.error(f"Privileged session command error: {e}")
            result.status = TaskStatus.FAILED
            result.stderr = str(e)
            result.return_code = -1

        result.end_time = time.time()
        result.execution_time = result.end_time - result.start_time
        return result

    @staticmethod
    def _apply_privileged_result(
        result: TaskResult, stdout: str, exit_code: int, timeout: Optional[float]
    ) -> None:
        """Fill a TaskResult from PrivilegedShell.run(); -1 means its marker never arrived."""
        result.stdout = stdout
        result.return_code = exit_code
        if exit_code == -1:
            result.status = TaskStatus.TIMEOUT
            result.stderr = (
                f"Command did not finish within {timeout} seconds and was interrupted"
            )
        else:
            result.status = TaskStatus.COMPLETED if exit_code == 0 else TaskStatus.FAILED


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
            remote_pid: Optional[int] = None
            channel = None
            try:
                self.logger.info(f"Executing synchronous command: {command}")
                track_pid = self._track_remote_pid()
                remote_command = (
                    f'echo "{_PID_MARKER}$$"; {command}' if track_pid else command
                )
                stdin, stdout, stderr = self.ssh_client.exec_command(
                    remote_command, timeout=timeout
                )
                channel = stdout.channel
                deadline = (start_time + timeout) if timeout else None

                def _on_pid(pid: int) -> None:
                    nonlocal remote_pid
                    remote_pid = pid

                stdout_data, stderr_data = self._collect_channel_output(
                    channel, deadline, track_pid, _on_pid
                )
                exit_code = channel.recv_exit_status()

                result.return_code = exit_code
                result.stdout = stdout_data
                result.stderr = stderr_data
                result.status = (
                    TaskStatus.COMPLETED if exit_code == 0 else TaskStatus.FAILED
                )
                break  # success

            except socket.timeout:
                # The step's duration was exceeded — not a transport failure.
                # Closing a non-PTY channel does not stop the remote command, so
                # kill its process group when we know it.
                if remote_pid:
                    self._kill_remote_process_group(remote_pid)
                if channel is not None:
                    try:
                        channel.close()
                    except Exception:
                        pass
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

    @staticmethod
    def _collect_channel_output(
        channel, deadline: Optional[float], track_pid: bool, on_pid
    ) -> Tuple[str, str]:
        """
        Drain stdout and stderr together until the command exits.

        Reading both streams at once avoids the deadlock where a command blocks
        on a full stderr buffer while we wait on stdout. ``deadline`` is an
        absolute time for the whole command (raises ``socket.timeout`` when
        passed). With ``track_pid`` the leading PID-marker line is stripped and
        handed to ``on_pid`` as soon as it arrives.
        """
        out, err = bytearray(), bytearray()
        pid_pending = track_pid
        marker = _PID_MARKER.encode("ascii")

        def take_marker(final: bool) -> None:
            # Byte-level so a multi-byte character split across chunks is never altered.
            nonlocal out, pid_pending
            if out.startswith(marker):
                newline = out.find(b"\n")
                if newline == -1 and not final:
                    return
                end = newline if newline != -1 else len(out)
                value = bytes(out[len(marker):end]).strip()
                if value.isdigit():
                    on_pid(int(value))
                out = out[end + 1:] if newline != -1 else bytearray()
                pid_pending = False
            elif final or len(out) >= len(marker) or not marker.startswith(bytes(out)):
                pid_pending = False

        while True:
            busy = False
            if channel.recv_ready():
                out += channel.recv(65536)
                busy = True
                if pid_pending:
                    take_marker(final=False)
            if channel.recv_stderr_ready():
                err += channel.recv_stderr(65536)
                busy = True
            if not busy:
                if channel.exit_status_ready():
                    break
                if channel.closed:
                    # Transport/channel died mid-command: let the caller's
                    # reconnect-and-retry path handle it (as the old blocking read did).
                    raise paramiko.SSHException("Channel closed")
                if deadline is not None and time.time() > deadline:
                    raise socket.timeout("command exceeded its duration")
                time.sleep(0.05)
        if pid_pending:
            take_marker(final=True)
        return out.decode("utf-8", errors="ignore"), err.decode("utf-8", errors="ignore")

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