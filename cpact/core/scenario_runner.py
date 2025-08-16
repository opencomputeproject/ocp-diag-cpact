"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.
"""

from concurrent.futures import ThreadPoolExecutor
from core.step_executor import StepExecutor
from utils.logger_utils import TestLogger


class ScenarioRunner:
    def __init__(self, scenario, context, thread_executor=None, validate_continue=False):
        self.logger = TestLogger().get_logger()
        self.scenario = scenario
        self.context = context
        self.executor_continue = thread_executor or ThreadPoolExecutor(max_workers=5)
        self.validate_continue = validate_continue

    def run(self):
        self.logger.info(f"Running scenario: {self.scenario.get('test_name')}")
        data = self.scenario
        steps = data.get("test_steps", [])
        self.context.set("test_id", data.get("test_id"))
        for step in steps:
            executor = StepExecutor(data.get("test_id"), step, self.context, executor=self.executor_continue)
            output, status, message = executor.run(validate_continue=self.validate_continue)
            if not status:
                self.logger.error(f"Step '{step.get('step_name')}' failed: {message}")
                # if not step.get("continue", False):
                return None, False, f"Step execution failed: {message}"
            else:
                self.logger.info(f"Step '{step.get('step_name')}' completed successfully.")

        return None, True, "Scenario executed successfully."
