"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.
"""

import re
import os
import time

from executor.base_executor import BaseExecutor
from analysis.analysis_factory import AnalysisFactory
from system_connections.connection_factory import ConnectionFactory
from utils.logger_utils import TestLogger

class LogAnalyzer(BaseExecutor):
    def execute(self):
        conn_type = self.step.get("connection_type")
        connection_name = self.step.get("connection")
        connection_factory = ConnectionFactory.get_instance()
        connection = connection_factory.get_connection(connection_name, conn_type)
        if not connection:
            self.logger.error(f"Connection '{connection_name}' of type '{conn_type}' not found.")
            return None, False, f"Connection '{connection_name}' of type '{conn_type}' not found."
        
        
        local_log_dir = self.get_log_path()
        os.makedirs(local_log_dir, exist_ok=True)
        local_log_file = os.path.join(local_log_dir, f"{self.step.get('step_id')}_log_analyzer.log")

        log_path = self.step.get("log_analysis_path")
        connection.download_file(log_path, local_log_file)
        time.sleep(3)
        self.logger.info(f"Log path: {log_path}")
        log_content = ""
        with open(local_log_file, 'r', encoding="utf-8") as file:
            log_content = file.read()
        if not log_path or not os.path.exists(local_log_file) or not log_content:
            self.logger.error("Log path is required for LogAnalyzer step.")
            return None, False, "Log path is required for LogAnalyzer step."
        self.logger.info(f"Analyzing log: {local_log_dir}")
        self.logger.info(f"Log content: {log_content[:100]}...")  # Log first 100 characters for brevity
        
        diagnostic_analysis = self.step.get("diagnostic_analysis")
        if diagnostic_analysis:
            analyzer_cls = AnalysisFactory.get_analyzer("diagnostic_analysis")
            analyzer = analyzer_cls(diagnostic_analysis)
            diag_result = analyzer.analyze(log_content, self.context)
            self.logger.info(f"[LogAnalyzer] Diagnostic Analysis: {diag_result}")
            
        return log_content, True, "Log analyzed successfully."
    
    def get_log_path(self):
        log_dir = TestLogger().get_log_dir()
        return os.path.join(log_dir, "step_logs")
    
    def get_log_data(self):
        log_path = self.get_log_path()
        if os.path.exists(log_path) and os.path.isfile(log_path):
            with open(log_path, 'r', encoding="utf-8") as file:
                return file.read()
        return ""
