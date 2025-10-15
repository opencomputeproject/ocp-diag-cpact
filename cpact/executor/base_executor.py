"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

===========================================================================
BaseExecutor is an abstract base class for implementing step-level execution logic
within a test scenario. It provides a standardized interface and shared context for
executors that handle different step types such as command execution, log analysis,
and scenario invocation.

Features:
- Stores step metadata and execution context.
- Supports threaded execution for continued steps.
- Integrates with centralized logging via TestLogger.
- Defines an abstract `execute()` method for custom step logic.
- Designed to be extended by specific executor implementations.

Classes:
    BaseExecutor:
        Abstract class for step execution logic in test scenarios.

Usage:
    Subclass BaseExecutor and implement the `execute()` method.
    Use `scenario_step` and `context` to access step details and shared state.
    Optionally use `thread_executor` for parallel or deferred execution.
===========================================================================
"""

from abc import ABC, abstractmethod
from utils.logger_utils import TestLogger
import ocptv.output as tv
from concurrent.futures import ThreadPoolExecutor
from core.context import Context


class BaseExecutor(ABC):
    def __init__(
        self,
        scenario_step: tv.step,
        context: Context,
        executor: ThreadPoolExecutor = None,
        validate_continue: bool = False,
    ) -> None:
        """
        Initializes the BaseExecutor with a scenario step, context, and optional thread executor for continued steps.
        Args:
            scenario_step (tv.step): The test step to be executed.
            context (Context): The shared context for storing and managing data.
            executor (ThreadPoolExecutor): Optional thread pool executor for handling continued steps.
            validate_continue (bool): Flag to indicate if continued steps should be validated.
        Returns:
            None
        """
        self.logger = TestLogger().get_logger()
        self.logger.info(
            f"Initializing {self.__class__.__name__} with step: {scenario_step}"
        )
        self.scenario_step = scenario_step
        self.step = scenario_step.step_details
        self.context = context
        self.thread_executor = executor
        self.validate_continue = validate_continue

    @abstractmethod
    def execute(self) -> tuple[str, bool, str]:
        """
        Executes the step logic and returns the result.

        Returns:
            tuple: A tuple containing output (str), status (bool), and message (str).
        """
        pass
