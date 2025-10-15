"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

===========================================================================
ExecutorFactory is a utility class that provides a centralized mechanism for retrieving
the appropriate executor class based on the step type defined in a test scenario. It supports
dynamic execution of commands, log analysis, and scenario invocation.

Features:
- Maps step types to corresponding executor classes.
- Supports extensibility for additional step types.
- Raises descriptive errors for unsupported step types.

Classes:
    ExecutorFactory:
        Provides a static method to retrieve executor classes by step type.

Supported Step Types:
    - "command_execution": Returns CommandExecutor
    - "log_analysis": Returns LogAnalyzer
    - "invoke_scenario": Returns ScenarioInvoker

Usage:
    Call `ExecutorFactory.get_executor("command_execution")` to retrieve the appropriate class.
    Instantiate the returned class with scenario step and context to execute the step.
===========================================================================
"""
from executor.command_executor import CommandExecutor
from executor.log_analyzer import LogAnalyzer
from executor.scenario_invoker import ScenarioInvoker
from typing import Type

class ExecutorFactory:
    EXECUTOR_MAP = {
        "command_execution": CommandExecutor,
        "log_analysis": LogAnalyzer,
        "invoke_scenario": ScenarioInvoker,
    }

    @staticmethod
    def get_executor(step_type: str) -> Type[CommandExecutor | LogAnalyzer | ScenarioInvoker]:
        """
        Returns the executor class based on the step type.
        Args:
            step_type (str): The type of the step to be executed.
        Returns:
            type: The executor class corresponding to the step type.
        """
        executor_cls = ExecutorFactory.EXECUTOR_MAP.get(step_type)
        if not executor_cls:
            raise ValueError(f"No executor found for step type: {step_type}")
        return executor_cls
