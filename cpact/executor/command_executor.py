"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

===========================================================================
CommandExecutor is a step-level executor responsible for running shell commands across
local, remote, or Docker-based environments. It supports synchronous and background execution,
output validation, and rule-based analysis, integrating with diagnostic tracking and structured logging.

Features:
- Executes commands via SSH, local shell, or Docker containers.
- Supports background execution and deferred validation for continued steps.
- Validates output against expected strings or files.
- Applies output analysis rules using regex-based diagnostics.
- Logs execution lifecycle and results using OCP TV and TestLogger.
- Integrates with Context and ResultCollector for diagnostic tracking.

Classes:
    CommandExecutor:
        Extends BaseExecutor to handle command execution steps in test scenarios.

Usage:
    Instantiate CommandExecutor with a scenario step and context.
    Call `execute()` to run the command and validate output.
    Automatically handles Docker execution, output analysis, and continued step finalization.
===========================================================================
"""

import os
import re
import time
import traceback
import subprocess
from core.context import Context
from concurrent.futures import ThreadPoolExecutor
from executor.base_executor import BaseExecutor
from analysis.analysis_factory import AnalysisFactory
from system_connections.connection_factory import ConnectionFactory
from system_connections.constants import ExecutionMode
from utils.docker_executor import DockerExecutor
from utils.logger_utils import TestLogger
from utils.validator import Validator
from result_builder.result_builder import ResultCollector
from ocptv.output import (
    DiagnosisType,
    LogSeverity,
    SoftwareType,
    TestResult,
    TestStatus,
)


class CommandExecutor(BaseExecutor):
    def execute(self) -> tuple[str, bool, str]:
        """
        Executes the command step by connecting to the specified system and running the command.
        Returns:
            tuple: A tuple containing output (str), status (bool), and message (str).
        """
        try:
            command = self.step.get("step_command")
            if not command:
                self.logger.error("No command provided in step data.")
                self.scenario_step.add_log(
                    LogSeverity.ERROR, "No command provided in step data."
                )
                return "", False, "No command provided in step data."

            if self.validate_continue:
                self.logger.info(
                    f"Validating continued step {self.step.get('step_id')} with command: {command}"
                )
                self.scenario_step.add_log(
                    LogSeverity.INFO,
                    f"Validating continued step {self.step.get('step_id')} with command: {command}",
                )
                output = self.validate_continued_step(self.step, self.context)
                if output["status"] == "fail":
                    return "", False, output["message"]
                return "", True, "Continued step validated successfully."

            continue_flag = self.step.get("continue", False)
            if continue_flag:
                output = self.run_continue_step(
                    self.step, self.context, self.thread_executor
                )
                self.logger.info(f"Continue step initiated: {output}")
                self.scenario_step.add_log(
                    LogSeverity.INFO, f"Continue step initiated: {output}"
                )
                return (
                    output,
                    True,
                    "Command execution started in background and will continue until completed.",
                )

            check_docker_step = self.check_docker_step(self.step)
            if check_docker_step:
                command = f'docker exec {self.step.get("container_name")} {command}'
                self.logger.info(f"Executing Docker command: {command}")
                self.scenario_step.add_log(
                    LogSeverity.INFO, f"Executing Docker command: {command}"
                )
                # return self.execute_docker_step(step=self.step, context=self.context)

            connection_name = self.step.get("connection")
            connection_type = self.step.get("connection_type")
            if not connection_name or not connection_type:
                self.logger.error("Connection name or type not provided in step data.")
                self.scenario_step.add_log(
                    LogSeverity.ERROR,
                    "Connection name or type not provided in step data.",
                )
                return "", False, "Connection name or type not provided in step data."
            self.logger.info(
                f"Executing command: {command} on connection: {connection_name} with type: {connection_type}"
            )
            self.scenario_step.add_log(
                LogSeverity.INFO,
                f"Executing command: {command} on connection: {connection_name} with type: {connection_type}",
            )
            factory = ConnectionFactory.get_instance()
            connection = factory.create_connection(connection_name, connection_type)
            connection.connect()
            if not connection.is_connected():
                self.logger.error(
                    f"Failed to connect to {connection_name} of type {connection_type}."
                )
                self.scenario_step.add_log(
                    LogSeverity.ERROR,
                    f"Failed to connect to {connection_name} of type {connection_type}.",
                )
                return (
                    "",
                    False,
                    f"Failed to connect to {connection_name} of type {connection_type}.",
                )
            self.logger.info(
                f"Started executing command: {command} on connection: {connection_name} with type: {connection_type}"
            )
            self.scenario_step.add_log(
                LogSeverity.INFO,
                f"Started executing command: {command} on connection: {connection_name} with type: {connection_type}",
            )
            result = connection.execute_command(
                command,
                mode=ExecutionMode.SYNCHRONOUS,
            )
            output = result.stdout
            if not output:
                self.logger.error(f"Command execution failed: {command}")
                self.scenario_step.add_log(
                    LogSeverity.ERROR, f"Command execution failed: {command}"
                )
                return "", False, "Command execution failed."
            log_dir = TestLogger().get_log_dir()
            output_dir = os.path.join(log_dir, "command_outputs")
            os.makedirs(output_dir, exist_ok=True)
            step_id = self.step.get("step_id", f"step_{int(time.time())}")
            step_name = re.sub(r"\W+", "_", self.step.get("step_name", "unnamed_step"))
            output_file_name = (
                f"{self.context.get('test_id')}_{step_id}_{step_name}.txt"
            )
            output_path = os.path.join(output_dir, output_file_name)
            with open(output_path, "w") as f:
                f.write(output)
            self.logger.info(f"Command output written to: {output_path}")
            self.logger.info(f"Command executed successfully: {command}")
            self.logger.info(f"Command output: {output}")
            self.scenario_step.add_log(
                LogSeverity.INFO, f"Command executed successfully: {command}"
            )
            output_analysis = self.step.get("output_analysis")
            if output_analysis:
                self.logger.info(
                    f"Output analysis enabled with rules: {output_analysis}"
                )
                self.scenario_step.add_log(
                    LogSeverity.INFO,
                    f"Output analysis enabled with rules: {output_analysis}",
                )
                self.output_analysis(output, output_analysis)

            expected_output = self.step.get("expected_output")
            expected_output_path = self.step.get("expected_output_path")
            if expected_output or expected_output_path:
                output, status, message = self.output_validation(
                    output, expected_output, expected_output_path
                )
                if not status:
                    return output, False, message
                self.logger.info(
                    f"Output validation status: {status}, message: {message}"
                )
                self.scenario_step.add_log(
                    LogSeverity.INFO,
                    f"Output validation status: {status}, message: {message}",
                )
            return output, True, "Command executed successfully and output validated."
        except AssertionError as e:
            tb_str = "".join(traceback.format_exception(type(e), e, e.__traceback__))
            self.logger.error(f"Formatted traceback:\n{tb_str}")
            self.logger.error(f"Output validation failed: {e}")
            self.logger.error(f"Output validation failed: {e}")
            return output, False, str(e)
        except KeyError as e:
            tb_str = "".join(traceback.format_exception(type(e), e, e.__traceback__))
            self.logger.error(f"Formatted traceback:\n{tb_str}")
            self.logger.error(f"Key error during command execution: {e}")
            self.scenario_step.add_log(
                LogSeverity.ERROR, f"Key error during command execution: {str(e)}"
            )
            return "", False, f"Key error during command execution: {str(e)}"
        except Exception as e:
            tb_str = "".join(traceback.format_exception(type(e), e, e.__traceback__))
            self.logger.error(f"Formatted traceback:\n{tb_str}")
            self.logger.error(f"Command execution failed: {str(e)}")
            return "", False, str(e)

    def output_analysis(self, output: str, output_analysis: list) -> None:
        """
        Analyzes the command output using defined output analyses.
        Args:
            output (str): The command output to be analyzed.
            output_analysis (list): List of output analysis rules.
        Returns:
            None"""
        analyzer_cls = AnalysisFactory.get_analyzer("output_analysis")
        analyzer = analyzer_cls(output_analysis, step_id=self.step.get("step_id"))
        out_result = analyzer.analyze(output, self.context)
        self.logger.info(f"[LogAnalyzer] Output Analysis: {out_result}")
        self.scenario_step.add_log(
            LogSeverity.INFO, f"[LogAnalyzer] Output Analysis: {out_result}"
        )

    def output_validation(
        self, output: str, expected_output: str, expected_output_path: str = None
    ) -> tuple[str, bool, str]:
        """
        Validates the command output against the expected output or expected output file.
        Args:
            output (str): The command output to be validated.
            expected_output (str): The expected output string.
            expected_output_path (str): Path to the file containing the expected output.
        Returns:
            tuple: A tuple containing output (str), status (bool), and message (str).
        """
        try:
            if not expected_output and not expected_output_path:
                self.logger.warning(
                    "No expected output or expected output path provided. Skipping validation."
                )
                self.scenario_step.add_warning(
                    "No expected output or expected output path provided. Skipping validation."
                )
                return (
                    output,
                    True,
                    "No expected output or expected output path provided. Skipping validation.",
                )
            if expected_output_path and expected_output:
                self.logger.info(
                    f"Both expected_output and expected_output_path are provided. Using expected_output_path for validation."
                )
                self.scenario_step.add_log(
                    LogSeverity.INFO,
                    f"Both expected_output and expected_output_path are provided. Using expected_output_path for validation.",
                )
                with open(expected_output_path, "r") as file:
                    expected_output = file.read()
            if expected_output_path:
                with open(expected_output_path, "r") as file:
                    expected_output = file.read()
            status, message = Validator._search_recursive(
                expected=expected_output,
                actual=output,
                use_regex=True,
                use_fuzzy=False,
                fuzzy_threshold=0.8,
            )

            return output, status, message
        except AssertionError as e:
            tb_str = "".join(traceback.format_exception(type(e), e, e.__traceback__))
            self.logger.error(f"Formatted traceback:\n{tb_str}")
            self.logger.error(f"Output validation failed: {e}")
            self.scenario_step.add_log(
                LogSeverity.ERROR, f"Output validation failed: {e}"
            )
            return output, False, str(e)
        except Exception as e:
            tb_str = "".join(traceback.format_exception(type(e), e, e.__traceback__))
            self.logger.error(f"Formatted traceback:\n{tb_str}")
            self.logger.error(f"Command execution failed: {e}")
            self.scenario_step.add_log(
                LogSeverity.ERROR, f"Command execution failed: {e}"
            )
            return "", False, str(e)

    def run_continue_step(
        self, step: dict, context: Context, executor: ThreadPoolExecutor
    ) -> dict:
        """
        Executes a command in continue mode, allowing it to run in the background.
        Args:
            step (dict): The step definition containing command and connection details.
            context (Context): The context object to manage continued steps.
            executor: The thread executor to manage background tasks.
        Returns:
            dict: A dictionary containing the status and message of the continue step initiation.
        """
        connection = step.get("connection")
        connection_type = step.get("connection_type")
        command = step["step_command"]
        step_id = step["step_id"]
        log_dir = TestLogger().get_log_dir()
        output_dir = os.path.join(log_dir, "continued_steps")
        os.makedirs(output_dir, exist_ok=True)
        stdout_path = os.path.join(output_dir, f"{step_id}_stdout.txt")
        stderr_path = os.path.join(output_dir, f"{step_id}_stderr.txt")
        out = open(stdout_path, "w")
        err = open(stderr_path, "w")
        check_docker_step = self.check_docker_step(self.step)
        if check_docker_step:
            command = f'docker exec {step.get("container_name")} {command}'
            self.logger.info(f"Executing Docker command: {command}")
            self.scenario_step.add_log(
                LogSeverity.INFO, f"Executing Docker command: {command}"
            )
        factory = ConnectionFactory.get_instance()
        connection = factory.create_connection(connection, connection_type)
        if not connection.is_connected():
            self.logger.info(f"Connecting to {connection} of type {connection_type}.")
            self.scenario_step.add_log(
                LogSeverity.INFO,
                f"Connecting to {connection} of type {connection_type}.",
            )
            if not connection.connect():
                self.logger.error(
                    f"Failed to connect to {connection} of type {connection_type}."
                )
                self.scenario_step.add_log(
                    LogSeverity.ERROR,
                    f"Failed to connect to {connection} of type {connection_type}.",
                )
                return (
                    "",
                    False,
                    f"Failed to connect to {connection} of type {connection_type}.",
                )
        self.logger.info(
            f"Started executing continue command: {command} on connection: {connection} with type: {connection_type}"
        )
        self.scenario_step.add_log(
            LogSeverity.INFO,
            f"Started executing continue command: {command} on connection: {connection} with type: {connection_type}",
        )
        task_result = connection.execute_command(
            command,
            mode=ExecutionMode.BACKGROUND,
        )
        context.add_continued_step(
            self.context.get("test_id"),
            step_id,
            {
                "step": self.scenario_step,
                "type": "subprocess",
                "connection": connection,
                "task_id": task_result.task_id,
                "stdout": task_result.stdout,
                "validated": False,
            },
        )

        return {"status": "continued", "message": f"{step_id} running in background"}

    def validate_continued_step(self, step: dict, context: Context) -> dict:
        """
        Validates the output of a previously initiated continue step.
        Args:
            step (dict): The step definition containing command and connection details.
            context (Context): The context object to manage continued steps.
        Returns:
            dict: A dictionary containing the status and message of the continued step validation.
        """
        step_id = step.get("step_id")

        if (
            not step_id
            or step_id not in context.continued_steps[context.get("scenario_id")]
        ):
            return {"status": "fail", "error": f"Invalid step_id: {step_id}"}
        step_info = context.continued_steps[context.get("scenario_id")][step_id]
        # future = step_info["future"]
        output = ""
        self.logger.info(f"Validating continued step: {step_id}")
        self.scenario_step.add_log(
            LogSeverity.INFO, f"Validating continued step: {step_id}"
        )
        try:
            scenario_step = context.continued_steps[context.get("scenario_id")][
                step_id
            ]["step"]
            step = (
                scenario_step.step_details if scenario_step else step_info.get("step")
            )
            # mark as validated
            context.continued_steps[context.get("scenario_id")][step_id][
                "validated"
            ] = True
            connection = step_info.get("connection")
            task_id = step_info.get("task_id")
            output, err, exit_code, status = connection.wait_for_task_with_details(
                task_id=task_id,
                wait=True,
                timeout=step.get("duration", 30),  # wait for it if still running
            )

            self.logger.info(f"Output for continued step {step_id}: {output}")
            self.scenario_step.add_log(
                LogSeverity.INFO, f"Output for continued step {step_id}: {output}"
            )
            output_analysis = step.get("output_analysis")
            if output_analysis:
                self.logger.info(
                    f"Output analysis enabled with rules: {output_analysis}"
                )
                self.scenario_step.add_log(
                    LogSeverity.INFO,
                    f"Output analysis enabled with rules: {output_analysis}",
                )
                self.output_analysis(output, output_analysis)

            expected_output = step.get("expected_output")
            expected_output_path = step.get("expected_output_path")
            self.logger.info(
                f"Expected output: {expected_output}, Expected output path: {expected_output_path}"
            )
            self.scenario_step.add_log(
                LogSeverity.INFO,
                f"Expected output: {expected_output}, Expected output path: {expected_output_path}",
            )
            if expected_output or expected_output_path:
                self.logger.info(
                    f"Validating output against expected output: {expected_output}"
                )
                output, status, message = self.output_validation(
                    output, expected_output, expected_output_path
                )
                self.logger.info(
                    f"Output validation status: {status}, message: {message}"
                )
                self.scenario_step.add_log(
                    LogSeverity.INFO,
                    f"Output validation status: {status}, message: {message}",
                )
                ResultCollector().get_instance().update_step_result(
                    step_id=step.get("step_id"),
                    step_name=step.get("step_name"),
                    step_type=step.get("step_type"),
                    status="success" if status else "fail",
                    duration=round(time.time() - self.context.get("start_time"), 3),
                    message=message,
                )
                if not status:
                    return {
                        "status": "fail",
                        "message": f"Validated continued step: {step_id}",
                    }

            return {"status": "pass", "message": f"Validated continued step: {step_id}"}

        except Exception as e:
            self.logger.error(f"Error validating continued step {step_id}: {e}")
            self.scenario_step.add_log(
                LogSeverity.ERROR,
                f"Error validating continued step {step_id}: {str(e)}",
            )
            import traceback

            traceback.print_exc()
            return {"status": "fail", "message": str(e)}

    def check_docker_step(self, step: dict) -> bool:
        """
        Checks if the step is a Docker command step.
        Args:
            step (dict): The step definition.
        Returns:
            bool: True if it's a Docker command step, False otherwise.
        """
        if step.get("container_name"):
            return True
        return False

    def execute_docker_step(
        self, step: dict, context: Context = None
    ) -> tuple[str, bool, str]:
        """
        Executes a command inside a Docker container.
        Args:
            step (dict): The step definition containing command and connection details.
            context (Context): The context object to manage continued steps.
        Returns:
            tuple: A tuple containing output (str), status (bool), and message (str).
        """
        docker_container = step.get("container_name")
        docker_executor = (
            context.get("docker_steps").get(docker_container)
            if context
            else self.context.get("docker_steps").get(docker_container)
        )
        if docker_executor:
            output, status, message = docker_executor.execute_command(
                step.get("step_command"),
                connection_name=step.get("connection"),
                container_name=docker_container,
                connection_type=step.get("connection_type"),
                use_sudo=step.get("use_sudo", False),
                duration=step.get("duration", 30),
            )
            return output, status, message
        else:
            self.logger.error(
                f"Docker container {docker_container} not found in context."
            )
            self.scenario_step.add_log(
                LogSeverity.ERROR,
                f"Docker container {docker_container} not found in context.",
            )
            return (
                "",
                False,
                f"Docker container {docker_container} not found in context.",
            )
