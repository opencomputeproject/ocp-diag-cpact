"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.
"""

from executor.command_executor import CommandExecutor
from executor.log_analyzer import LogAnalyzer
from executor.scenario_invoker import ScenarioInvoker

class ExecutorFactory:
    EXECUTOR_MAP = {
        "command_execution": CommandExecutor,
        "log_analysis": LogAnalyzer,
        "invoke_scenario": ScenarioInvoker
    }

    @staticmethod
    def get_executor(step_type: str):
        executor_cls = ExecutorFactory.EXECUTOR_MAP.get(step_type)
        if not executor_cls:
            raise ValueError(f"No executor found for step type: {step_type}")
        return executor_cls
