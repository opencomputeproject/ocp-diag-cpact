"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

===============================================================================
DockerExecutor is a utility class for managing Docker container lifecycle operations
within automated test scenarios. It supports both local and remote container execution
via SSH or other connection types, and integrates with a centralized logging system.

Features:
- Starts, executes commands in, and stops Docker containers.
- Supports remote execution using connection abstractions.
- Stops all running containers when needed.
- Logs container operations and command outputs.
- Handles container configuration via structured step data.

Attributes:
    docker_steps (dict): Configuration for the Docker step.
    docker_index (int): Index of the step in the test scenario.
    container_id (str): ID of the running container.
    use_sudo (bool): Whether to prefix commands with sudo.
    logger (Logger): Logger instance for structured output.

Usage:
    Instantiate DockerExecutor with step data and index.
    Call `load_docker()` to start the container.
    Use `execute_command()` to run commands inside the container.
    Call `stop_container()` or `stop_all_containers()` (CPACT-labelled containers only) to clean up after execution.
===============================================================================
"""

import re
import shlex
import time
from typing import List, Optional, Sequence, Tuple, Union

import docker

from cpact.system_connections.connection_factory import ConnectionFactory
from cpact.system_connections.local_connection import LocalConnection
from cpact.utils.logger_utils import TestLogger
from cpact.system_connections.constants import ExecutionMode

# Docker's own container-name rule; also guarantees the name is shell-safe.
_CONTAINER_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
# Image reference ([registry[:port]/]repo[:tag][@digest]) without shell metacharacters.
_IMAGE_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/:@-]*$")
_SHELL_PATH_RE = re.compile(r"^[A-Za-z0-9_./-]+$")
# Every container CPACT starts carries this label so cleanup never touches
# containers it does not own.
_MANAGED_LABEL = "cpact.managed=true"
# cmd.exe has no reliable escape for these inside a quoted argument: '"' ends the
# quoted region (exposing & | < > to cmd) and %VAR% is expanded even in quotes.
_CMD_UNQUOTABLE_RE = re.compile(r'["%\r\n]')
_CMD_SAFE_ARG_RE = re.compile(r"^[A-Za-z0-9_./:=,@+\\-]+$")


def _quote_windows_arg(arg: str) -> str:
    if _CMD_UNQUOTABLE_RE.search(arg):
        raise ValueError(
            f"Argument {arg!r} cannot be safely quoted for cmd.exe "
            "(double quotes, % and newlines are not supported)"
        )
    if _CMD_SAFE_ARG_RE.match(arg):
        return arg
    # Inside "..." cmd.exe treats & | < > ^ ( ) literally; trailing backslashes
    # must be doubled so they don't escape the closing quote (MSVC rules).
    return '"' + re.sub(r"(\\+)$", r"\1\1", arg) + '"'


def validate_container_name(name: str) -> str:
    """Return ``name`` if it is a valid Docker container name, else raise ValueError."""
    if not isinstance(name, str) or not _CONTAINER_NAME_RE.match(name):
        raise ValueError(
            f"Invalid container_name {name!r}: must match [A-Za-z0-9][A-Za-z0-9_.-]*"
        )
    return name


def validate_image(image: str) -> str:
    """Return ``image`` if it is a plain Docker image reference, else raise ValueError."""
    if not isinstance(image, str) or not _IMAGE_REF_RE.match(image):
        raise ValueError(
            f"Invalid container_image {image!r}: only letters, digits and ._/:@- are allowed"
        )
    return image


def quote_command(args: Sequence[str], connection: object) -> str:
    """Join ``args`` into one command string quoted for the connection's shell.

    Raises ValueError for arguments that cannot be quoted safely for cmd.exe
    on a Windows local connection.
    """
    if isinstance(connection, LocalConnection) and connection.is_windows:
        return " ".join(_quote_windows_arg(str(arg)) for arg in args)
    return " ".join(shlex.quote(str(arg)) for arg in args)


class DockerExecutor:
    def __init__(self, step_data: dict, step_index: int) -> None:
        """
        Initializes the DockerExecutor with step data and index.
        Args:
            step_data (dict): The Docker step configuration.
            step_index (int): The index of the step in the scenario.
        Returns:
            None
        """
        self.docker_steps = step_data
        self.docker_index = step_index
        self.container_id = None
        self.use_sudo = False
        self.logger = TestLogger().get_logger()

    def load_docker(self: object) -> None:
        """
        remote_container_name: prime95-test
        image: prime95-stress
        container_name: prime95-test
        duration: 30
        log_dir: /tmp/container_logs
        log_path: /tmp/container_logs/test.log
        container_location: target

        """
        # self.stop_container()

        container_name = validate_container_name(
            self.docker_steps.get("container_name", "prime95-test")
        )
        container_image = validate_image(
            self.docker_steps.get("container_image", "prime95-stress")
        )
        connection_name = self.docker_steps.get("connection", "Inband")
        connection_type = self.docker_steps.get("connection_type", "ssh")
        container_location = self.docker_steps.get("container_location", "local")
        self.use_sudo = self.docker_steps.get("use_sudo", False)
        self.logger.info(f"\n🚀 Starting container: {container_name}")
        start_cmd = [
            "docker", "run", "-dit",
            "--label", _MANAGED_LABEL,
            "--name", container_name, container_image,
        ]
        self.logger.info(f"Executing command to start container: {' '.join(start_cmd)}")
        self.container_id, err = self.execute(
            start_cmd,
            container_location=container_location,
            connection_name=connection_name,
            connection_type=connection_type,
            use_sudo=self.use_sudo,
        )
        self.logger.info(f"Container ID: {self.container_id}")
        if err or not self.container_id:
            self.logger.error(f"Failed to start container: {err}")
            raise RuntimeError(f"Failed to start container: {err}")
        self.logger.info(f"Container started with ID: {self.container_id}")
        # command = self.docker_steps.get("command", "prime95 -t")

    def execute_command(
        self,
        command: str,
        shell: str = "/bin/bash",
        container_name: str = "",
        container_location: str = "local",
        connection_name: str = None,
        connection_type: str = None,
        duration: int = 30,
        use_sudo: bool = False,
    ) -> tuple[str, bool, str]:
        """Executes a command in the Docker container.
        ``command`` is run by ``shell -c`` inside the container; it is passed as a
        single quoted argument so the host shell never interprets it.
        """
        if not _SHELL_PATH_RE.match(shell or ""):
            return "", False, f"Invalid shell {shell!r}"
        try:
            validate_container_name(container_name)
        except ValueError as e:
            return "", False, str(e)

        args = ["docker", "exec", container_name, shell, "-c", command]
        output, error = self.execute(
            args,
            container_location=container_location,
            connection_name=connection_name,
            connection_type=connection_type,
            use_sudo=use_sudo,
        )
        if error:
            self.logger.error(f"Error executing command: {error}")
            return "", False, f"Error executing command: {error}"
        time.sleep(duration)
        self.logger.info(f"Command executed successfully: {' '.join(args)}")
        self.logger.debug(f"Command output: {output}")
        return output, True, "Command executed successfully"

    def stop_container(self: object) -> None:
        """Stops and removes the Docker container."""
        container_name = validate_container_name(
            self.docker_steps.get("container_name", "prime95-test")
        )
        connection_name = self.docker_steps.get("connection", "Inband")
        connection_type = self.docker_steps.get("connection_type", "ssh")
        container_location = self.docker_steps.get("container_location", "local")
        self.logger.info(f"🛑 Stopping container: {self.container_id}")
        self.execute(
            ["docker", "stop", container_name],
            container_location=container_location,
            connection_name=connection_name,
            connection_type=connection_type,
            use_sudo=self.use_sudo,
        )
        self.logger.info(f"Container {container_name} stopped.")
        self.execute(
            ["docker", "rm", container_name],
            container_location=container_location,
            connection_name=connection_name,
            connection_type=connection_type,
            use_sudo=self.use_sudo,
        )
        self.logger.info(f"Container {container_name} removed.")

    def stop_all_containers(self: object) -> None:
        """Stops and removes the running containers started by CPACT (labelled)."""
        self.logger.info("🛑 Stopping all CPACT-managed containers.")
        try:
            client = docker.from_env()
            for container in client.containers.list(filters={"label": _MANAGED_LABEL}):
                self.logger.info(f"Stopping container: {container.name}")
                container.stop()
                container.remove()
                self.logger.info(f"Container {container.name} stopped and removed.")
        except Exception as e:
            self.logger.error(f"Error stopping containers: {e}")
            raise RuntimeError(f"Error stopping containers: {e}")

    def execute(
        self,
        command: Union[str, List[str]],
        container_location: str = "local",
        connection_name: str = None,
        connection_type: str = None,
        use_sudo: bool = False,
    ) -> Tuple[str, Optional[str]]:
        """
        Runs a docker CLI command on the configured connection.

        ``command`` should be an argument list; it is quoted for the target
        shell. Returns ``(stdout, error)`` where ``error`` is None on success.
        """
        self.logger.info(
            f"Using connection: {connection_name} of type {connection_type}"
        )
        factory = ConnectionFactory.get_instance()
        connection = factory.get_connection(connection_name, connection_type)
        if not connection:
            msg = f"Connection {connection_name} of type {connection_type} not found."
            self.logger.error(msg)
            return "", msg
        if not connection.is_connected():
            self.logger.info(
                f"Connecting to {connection_name} of type {connection_type}."
            )
            if not connection.connect():
                msg = f"Failed to connect to {connection_name} of type {connection_type}."
                self.logger.error(msg)
                return "", msg

        if not isinstance(command, str):
            try:
                command = quote_command(command, connection)
            except ValueError as e:
                self.logger.error(str(e))
                return "", str(e)
        self.logger.info(f"Executing docker command: {command}")
        result = connection.execute_command(
            command,
            mode=ExecutionMode.SYNCHRONOUS,
            use_sudo=use_sudo,
        )
        stdout = (getattr(result, "stdout", "") or "").strip()
        return_code = getattr(result, "return_code", None)
        if return_code not in (0, None):
            stderr = (getattr(result, "stderr", "") or "").strip()
            return stdout, stderr or f"exit code {return_code}"
        return stdout, None
