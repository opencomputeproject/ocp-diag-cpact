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
    Call `stop_container()` or `stop_all_containers()` to clean up after execution.
===============================================================================
"""
import time
import docker

from system_connections.connection_factory import ConnectionFactory
from utils.logger_utils import TestLogger
from system_connections.constants import ExecutionMode


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

        container_name = self.docker_steps.get("container_name", "prime95-test")
        container_image = self.docker_steps.get("container_image", "prime95-stress")
        connection_name = self.docker_steps.get("connection", "Inband")
        connection_type = self.docker_steps.get("connection_type", "ssh")
        container_location = self.docker_steps.get("container_location", "local")
        self.use_sudo = self.docker_steps.get("use_sudo", False)
        self.logger.info(f"\n🚀 Starting container: {container_name}")
        start_cmd = f"docker run -dit --name {container_name} {container_image}"
        self.logger.info(f"Executing command to start container: {start_cmd}")
        self.container_id, err = self.execute(
            start_cmd,
            container_location=container_location,
            connection_name=connection_name,
            connection_type=connection_type,
            use_sudo=self.use_sudo,
        )
        self.logger.info(f"Container ID: {self.container_id}")
        if not self.container_id:
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
        If the container is running locally, it uses subprocess to execute the command.
        If the container is running remotely, it uses SSH to execute the command.
        """

        command = f'docker exec {container_name} {shell} -c "{command}"'
        output, error = self.execute(
            command,
            container_location=container_location,
            connection_name=connection_name,
            connection_type=connection_type,
            use_sudo=use_sudo,
        )
        time.sleep(duration)
        if error:
            self.logger.error(f"Error executing command: {error}")
            return "", False, f"Error executing command: {error}"
        self.logger.info(f"Command executed successfully: {command}")
        self.logger.debug(f"Command output: {output}")
        return output, True, "Command executed successfully"

    def stop_container(self: object) -> None:
        """Stops and removes the Docker container."""
        container_name = self.docker_steps.get("container_name", "prime95-test")
        container_image = self.docker_steps.get("container_image", "prime95-stress")
        connection_name = self.docker_steps.get("connection", "Inband")
        connection_type = self.docker_steps.get("connection_type", "ssh")
        container_location = self.docker_steps.get("container_location", "local")
        self.logger.info(f"🛑 Stopping container: {self.container_id}")
        self.execute(
            f"docker stop {container_name}",
            container_location=container_location,
            connection_name=connection_name,
            connection_type=connection_type,
            use_sudo=self.use_sudo,
        )
        self.logger.info(f"Container {container_name} stopped.")
        self.execute(
            f"docker rm {container_name}",
            container_location=container_location,
            connection_name=connection_name,
            connection_type=connection_type,
            use_sudo=self.use_sudo,
        )
        self.logger.info(f"Container {container_name} removed.")

    def stop_all_containers(self: object) -> None:
        """Stops all running Docker containers."""
        self.logger.info("🛑 Stopping all running containers.")
        try:
            client = docker.from_env()
            for container in client.containers.list():
                self.logger.info(f"Stopping container: {container.name}")
                container.stop()
                container.remove()
                self.logger.info(f"Container {container.name} stopped and removed.")
        except Exception as e:
            self.logger.error(f"Error stopping containers: {e}")
            raise RuntimeError(f"Error stopping containers: {e}")

    def execute(
        self,
        command: str,
        container_location: str = "local",
        connection_name: str = None,
        connection_type: str = None,
        use_sudo: bool = False,
    ) -> tuple[str, bool]:
        """
        Executes a command in the Docker container.
        """
        # if container_location == "target":
        # For remote execution, use SSH or other remote command execution methods
        self.logger.info(f"Executing command on remote container: {command}")
        self.logger.info(
            f"Using connection: {connection_name} of type {connection_type}"
        )
        factory = ConnectionFactory.get_instance()
        connection = factory.get_connection(connection_name, connection_type)
        if not connection:
            self.logger.error(
                f"Connection {connection_name} of type {connection_type} not found."
            )
            return (
                "",
                False,
                f"Connection {connection_name} of type {connection_type} not found.",
            )
        if not connection.is_connected():
            self.logger.info(
                f"Connecting to {connection_name} of type {connection_type}."
            )
            if not connection.connect():
                self.logger.error(
                    f"Failed to connect to {connection_name} of type {connection_type}."
                )
                return (
                    "",
                    False,
                    f"Failed to connect to {connection_name} of type {connection_type}.",
                )
        output = connection.execute_command(
            command,
            mode=ExecutionMode.SYNCHRONOUS,
        )
        self.logger.info(f"Command executed successfully: {command}")
        return output, None
