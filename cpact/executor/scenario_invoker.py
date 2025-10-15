"""
Copyright (c) 2025 Open Compute Project.
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

=============================================================================
ScenarioInvoker is a step-level executor responsible for invoking nested test scenarios
from within a parent scenario. It loads and executes external scenario files, enabling
modular and reusable test design.

Features:
- Loads external scenario files using a defined path.
- Delegates execution to ScenarioRunner with shared context.
- Supports threaded execution and continued step validation.
- Enables hierarchical scenario composition and reuse.

Classes:
    ScenarioInvoker:
        Executes a referenced scenario file as part of a parent test step.

Usage:
    Instantiate ScenarioInvoker with a scenario step and context.
    Call `execute()` to load and run the nested scenario.
    Define `scenario_path` in the step to specify the external scenario file.
=============================================================================
"""
from utils.scenario_parser import load_yaml_file
from core.context import Context
import ocptv.output as tv
from concurrent.futures import ThreadPoolExecutor


class ScenarioInvoker:
    def __init__(
        self,
        scenario_step: tv.step,
        context: Context,
        thread_executor: ThreadPoolExecutor = None,
        validate_continue: bool = False,
    ) -> None:
        """
        Initializes the ScenarioInvoker with a scenario step, context, and optional thread executor for continued steps.
        Args:
            scenario_step (tv.step): The test step to be executed.
            context (Context): The shared context for storing and managing data.
            thread_executor (ThreadPoolExecutor): Optional thread pool executor for handling continued steps.
            validate_continue (bool): Flag to indicate if continued steps should be validated.
        Returns:
            None
        """
        self.scenario_step = scenario_step
        self.step = scenario_step.step_details if scenario_step else scenario_step
        self.context = context
        self.thread_executor = thread_executor
        self.validate_continue = validate_continue

    def execute(self) -> tuple[str, bool, str]:
        """
        Executes the scenario invocation logic and returns the result.
        Returns:
            tuple: A tuple containing output (str), status (bool), and message (str).
        """

        from core.scenario_runner import (
            ScenarioRunner,
        )  # Delayed import to avoid circular import

        scenario_path = self.step.get("scenario_path")
        if not scenario_path:
            raise ValueError("Scenario path is required for ScenarioInvoker step.")
        scenario = load_yaml_file(scenario_path)
        runner = ScenarioRunner(
            scenario["test_scenario"],
            self.context,
            thread_executor=self.thread_executor,
            validate_continue=self.validate_continue,
        )
        output, status, message = runner.run()
        return output, status, message
