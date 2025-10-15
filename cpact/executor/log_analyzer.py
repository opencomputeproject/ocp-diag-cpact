"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

===========================================================================
LogAnalyzer is a step-level executor responsible for analyzing log files using rule-based
diagnostic analysis. It supports local and remote log retrieval, dynamic path resolution,
and integration with diagnostic tracking and structured logging.

Features:
- Downloads logs from remote systems using configured connections.
- Resolves dynamic log paths using current log directory context.
- Applies diagnostic analysis rules using regex-based pattern matching.
- Logs execution lifecycle and analysis results using OCP TV and TestLogger.
- Integrates with Context and ResultCollector for diagnostic tracking.

Classes:
    LogAnalyzer:
        Extends BaseExecutor to handle log analysis steps in test scenarios.

Usage:
    Instantiate LogAnalyzer with a scenario step and context.
    Call `execute()` to retrieve and analyze logs.
    Define `diagnostic_analysis` rules in the step to enable pattern-based evaluation.
===========================================================================
"""
import re
import os
import time

from executor.base_executor import BaseExecutor
from analysis.analysis_factory import AnalysisFactory
from system_connections.connection_factory import ConnectionFactory
from utils.logger_utils import TestLogger
from ocptv.output import (
    DiagnosisType,
    LogSeverity,
    SoftwareType,
    TestResult,
    TestStatus,
)


class LogAnalyzer(BaseExecutor):
    def execute(self) -> tuple[str, bool, str]:
        """
        Executes the log analysis step by analyzing logs from a specified path using defined diagnostic analyses.
        Returns:
            tuple: A tuple containing output (str), status (bool), and message (str).
        """
        conn_type = self.step.get("connection_type")
        connection_name = self.step.get("connection")
        connection_factory = ConnectionFactory.get_instance()
        connection = connection_factory.get_connection(connection_name, conn_type)
        if not connection:
            self.logger.error(
                f"Connection '{connection_name}' of type '{conn_type}' not found."
            )
            self.scenario_step.add_log(
                LogSeverity.ERROR,
                f"Connection '{connection_name}' of type '{conn_type}' not found.",
            )
            return (
                None,
                False,
                f"Connection '{connection_name}' of type '{conn_type}' not found.",
            )
        self.scenario_step.add_log(
            LogSeverity.INFO,
            f"Using connection: {connection_name} of type: {conn_type}",
        )
        log_path = self.step.get("log_analysis_path")
        if "current_log_dir" in log_path:
            log_dir = TestLogger().get_log_dir()
            file_name = log_path.split("current_log_dir")[-1].lstrip("/\\")
            log_path = os.path.join(log_dir, "command_outputs", file_name)
            self.logger.info(f"Resolved log path: {log_path}")
            self.scenario_step.add_log(
                LogSeverity.INFO, f"Resolved log path: {log_path}"
            )
            local_log_dir = os.path.dirname(log_path)
            local_log_file = log_path
        else:
            local_log_dir = self.get_log_path()
            os.makedirs(local_log_dir, exist_ok=True)
            local_log_file = os.path.join(
                local_log_dir, f"{self.step.get('step_id')}_log_analyzer.log"
            )
            connection.download_file(log_path, local_log_file)
        time.sleep(3)
        self.logger.info(f"Log path: {log_path}")
        self.scenario_step.add_log(LogSeverity.INFO, f"Log path: {log_path}")
        log_content = ""
        with open(local_log_file, "r", encoding="utf-8") as file:
            log_content = file.read()
        if not log_path or not os.path.exists(local_log_file) or not log_content:
            self.logger.error("Log path is required for LogAnalyzer step.")
            self.scenario_step.add_log(
                LogSeverity.ERROR, "Log path is required for LogAnalyzer step."
            )
            return None, False, "Log path is required for LogAnalyzer step."
        self.logger.info(f"Analyzing log: {local_log_dir}")
        self.logger.info(
            f"Log content: {log_content[:100]}..."
        )  # Log first 100 characters for brevity
        self.scenario_step.add_log(LogSeverity.INFO, f"Analyzing log: {local_log_dir}")
        self.scenario_step.add_log(
            LogSeverity.INFO, f"Log content: {log_content[:100]}..."
        )  # Log first 100 characters for brevity

        diagnostic_analysis = self.step.get("diagnostic_analysis")
        if diagnostic_analysis:
            analyzer_cls = AnalysisFactory.get_analyzer("diagnostic_analysis")
            analyzer = analyzer_cls(
                diagnostic_analysis, step_id=self.step.get("step_id")
            )
            diag_result = analyzer.analyze(log_content, self.context)
            self.logger.info(f"[LogAnalyzer] Diagnostic Analysis: {diag_result}")
            self.scenario_step.add_log(
                LogSeverity.INFO, f"[LogAnalyzer] Diagnostic Analysis: {diag_result}"
            )

        return log_content, True, "Log analyzed successfully."

    def get_log_path(self) -> str:
        """
        Returns the directory path where logs should be stored.
        Returns:
            str: The directory path for storing logs.
        """
        log_dir = TestLogger().get_log_dir()
        return os.path.join(log_dir, "step_logs")

    def get_log_data(self) -> str:
        """
        Reads and returns the content of the log file.
        Returns:
            str: The content of the log file.
        """
        log_path = self.get_log_path()
        if os.path.exists(log_path) and os.path.isfile(log_path):
            with open(log_path, "r", encoding="utf-8") as file:
                return file.read()
        return ""
