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
from typing import Optional
from datetime import datetime
import mimetypes

from cpact.executor.base_executor import BaseExecutor
from cpact.analysis.analysis_factory import AnalysisFactory
from cpact.system_connections.connection_factory import ConnectionFactory
from cpact.utils.logger_utils import TestLogger
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
        log_file_path = self.get_log_file(log_path)
        log_dir = TestLogger().get_log_dir()
        log_path = os.path.join(
            log_dir,
            "AnalyzedLogFiles",
            f"analyzed_{self.step.get('step_id', 'default')}.log",
        )

        if not os.path.exists(log_file_path) or not log_file_path:
            self.logger.error("Log path is required for LogAnalyzer step.")
            self.scenario_step.add_log(
                LogSeverity.ERROR, "Log path is required for LogAnalyzer step."
            )
            return None, False, "Log path is required for LogAnalyzer step."

        log_content = ""
        with open(log_file_path, "r", encoding="utf-8") as file:
            log_content = file.read()

        check = connection.download_file(log_file_path, log_path)

        time.sleep(3)

        self.logger.info(f"Log path: {log_path}")
        self.scenario_step.add_log(LogSeverity.INFO, f"Log path: {log_path}")
        self.logger.info(f"Analyzing log: {log_file_path}")
        self.logger.info(
            f"Log content: {log_content[:100]}..."
        )  # Log first 100 characters for brevity
        self.scenario_step.add_log(LogSeverity.INFO, f"Analyzing log: {log_file_path}")
        self.scenario_step.add_log(
            LogSeverity.INFO, f"Log content: {log_content[:100]}..."
        )  # Log first 100 characters for brevity

        diagnostic_analysis = self.step.get("diagnostic_analysis")
        validator_type = self.step.get("validator_type", "regex")
        if diagnostic_analysis:
            analyzer_cls = AnalysisFactory.get_analyzer("diagnostic_analysis")
            analyzer = analyzer_cls(
                diagnostic_analysis, step_id=self.step.get("step_id")
            )
            diag_result = analyzer.analyze(log_content, self.context, validator_type)
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

    def get_log_file(self, path_pattern: str) -> Optional[str]:
        """
        Finds the latest log file that matches the given path pattern.

        This method supports resolving static, dynamic, and regex-based file paths.
        It can interpret paths containing the special placeholder "current_log_dir"
        (representing the active log directory), as well as those that include a
        `Regex(...)` expression to match variable directory or file names.

        The function searches for files that match the pattern and returns the
        most recently modified one. It logs key steps during path resolution
        and search execution.

        Args:
            path_pattern (str):
                The path pattern used to locate the log file. It can include:
                - Exact absolute or relative file paths.
                - The placeholder `"current_log_dir"` to reference the current log directory.
                - A regex expression wrapped inside `Regex(...)` to dynamically match paths.

                Examples:
                    - `"../sample_workspace/logs/test_run_Regex([\\d+\\w+\\s+]*)/test_run.log"`
                    - `"../sample_workspace/test_run_Regex([\\d+\\w+\\s+]*).log"`

        Returns:
            Optional[str]:
                The absolute path of the latest matching log file if found;
                otherwise, `None` if no file matches the pattern or the base
                directory cannot be located.

        Logging:
            This method logs:
                - Path resolution steps.
                - Regex pattern interpretation.
                - Search progress and results.
                - Warnings if no matches are found or invalid paths are provided.

        Examples:
            >>> get_log_file("../workspace/logs/test_run_Regex([0-9]+)/output.log")
            "/home/user/workspace/logs/test_run_123/output.log"

            >>> get_log_file("../workspace/logs/nonexistent.log")
            None
        """
        if not path_pattern:
            return ""

        # -------------------------------------------------------------------------
        # 🧩 1. Handle "current_log_dir" placeholder
        # -------------------------------------------------------------------------
        if "current_log_dir" in path_pattern:
            log_dir = TestLogger().get_log_dir()
            file_part = path_pattern.split("current_log_dir", 1)[-1].lstrip("/\\")
            path_pattern = os.path.join(log_dir, "command_outputs", file_part)

            self.logger.info(f"Resolved log path: {path_pattern}")
            self.scenario_step.add_log(
                LogSeverity.INFO, f"Resolved log path: {path_pattern}"
            )

        # -------------------------------------------------------------------------
        # 🧩 2. Resolve relative paths
        # -------------------------------------------------------------------------
        if not os.path.isabs(path_pattern):
            path_pattern = os.path.abspath(path_pattern)
            self.logger.info(f"Resolved relative path to absolute: {path_pattern}")
            self.scenario_step.add_log(
                LogSeverity.INFO, f"Resolved relative path to absolute: {path_pattern}"
            )

        # -------------------------------------------------------------------------
        # 🧩 3. Detect Regex(...) in path
        # -------------------------------------------------------------------------
        regex_match = re.search(r"Regex\((.*?)\)", path_pattern)
        if not regex_match:
            # No regex → treat as a normal file
            if os.path.exists(path_pattern):
                return os.path.abspath(path_pattern)
            msg = f"⚠️ File not found: {path_pattern}"
            self.logger.error(msg)
            self.scenario_step.add_log(LogSeverity.ERROR, msg)
            return ""

        # Extract regex inside parentheses
        regex_expr = regex_match.group(1)
        pre_regex = path_pattern[: regex_match.start()]
        post_regex = path_pattern[regex_match.end() :]

        # Find the directory to start searching
        search_dir = pre_regex
        while not os.path.isdir(search_dir) and search_dir:
            search_dir = os.path.dirname(search_dir)
        if not search_dir:
            msg = f"⚠️ Base directory not found for pattern: {path_pattern}"
            self.logger.info(msg)
            self.scenario_step.add_log(LogSeverity.INFO, msg)
            return ""

        self.logger.info(f"Searching under base directory: {search_dir}")
        self.scenario_step.add_log(
            LogSeverity.INFO, f"Searching under base directory: {search_dir}"
        )

        # -------------------------------------------------------------------------
        # 🧩 4. Build regex for relative path
        # -------------------------------------------------------------------------
        regex_path = (
            pre_regex[len(search_dir) + 1 :]
            + regex_expr
            + (os.sep if self.is_known_file_extension(post_regex) else "")
            + os.sep
            + post_regex
        )
        regex_path = re.sub(r"//+", "/", regex_path)  # clean slashes
        matched_files = []
        for dirpath, _, filenames in os.walk(search_dir):
            for filename in filenames:
                full_path = os.path.join(dirpath, filename)
                rel_path = os.path.relpath(full_path, search_dir)
                if re.fullmatch(regex_path, rel_path):
                    matched_files.append(full_path)

        # -------------------------------------------------------------------------
        # 🧩 5. Handle matches
        # -------------------------------------------------------------------------
        if not matched_files:
            msg = f"⚠️ No files matched regex pattern: {path_pattern}"
            self.logger.info(msg)
            self.scenario_step.add_log(LogSeverity.INFO, msg)
            return ""

        matched_files.sort(key=lambda f: os.path.getmtime(f), reverse=True)
        latest = os.path.abspath(matched_files[0])
        ts = datetime.fromtimestamp(os.path.getmtime(latest)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        msg = f"✅ Latest matching file: {latest} (Modified: {ts})"
        self.logger.info(msg)
        self.scenario_step.add_log(LogSeverity.INFO, msg)
        return latest

    def is_regex_path(self, path: str) -> bool:
        """
        Determines whether a given path string contains regular expression meta characters.

        This method checks if the provided path includes regex-specific characters such as
        '*', '+', '?', '[', ']', '(', ')', '{', '}', '|', '^', or '$'. It ignores normal
        path components such as '.' or path separators ('/' or '\\').

        Args:
            path (str): The path string to check. It may include normal directory
                components or potential regex patterns.

        Returns:
            bool: True if the path contains any regex meta characters, False otherwise.

        Examples:
            >>> is_regex_path("/logs/test_run_.*.log")
            True
            >>> is_regex_path("../sample_workspace/logs/")
            False
        """
        regex_chars = set("*+?[](){}|^$")
        return any(ch in path for ch in regex_chars)

    def is_known_file_extension(self, ext: str) -> bool:
        """
        Checks whether a given string represents a valid file extension.

        A valid file extension starts with a dot ('.') followed by one or more
        alphanumeric characters, underscores, or additional dots. Examples of
        valid extensions include '.txt', '.tar.gz', '.py', and '.gitignore'.

        Args:
            s (str): The string to check. This may include or omit the leading dot.

        Returns:
            bool: True if the string is a valid file extension, otherwise False.

        Examples:
            >>> is_file_extension(".txt")
            True
            >>> is_file_extension("txt")
            False
            >>> is_file_extension(".tar.gz")
            True
            >>> is_file_extension(".")
            False
        """
        if not ext.startswith("."):
            return False
        mime = mimetypes.types_map.get(ext.lower())
        return mime is not None
