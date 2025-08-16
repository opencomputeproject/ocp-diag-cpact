"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.
"""

from utils.scenario_parser import load_yaml_file

class ScenarioInvoker:
    def __init__(self, step, context, thread_executor=None, validate_continue=False):
        self.step = step
        self.context = context
        self.thread_executor = thread_executor
        self.validate_continue = validate_continue

    def execute(self):
        from core.scenario_runner import ScenarioRunner  # Delayed import to avoid circular import
        scenario_path = self.step.get("scenario_path")
        if not scenario_path:
            raise ValueError("Scenario path is required for ScenarioInvoker step.")
        scenario = load_yaml_file(scenario_path)
        runner = ScenarioRunner(scenario["test_scenario"], self.context, thread_executor=self.thread_executor, validate_continue=self.validate_continue)
        output, status, message = runner.run()
        return output, status, message