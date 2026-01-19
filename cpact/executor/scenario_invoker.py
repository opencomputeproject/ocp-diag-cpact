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
import time
from datetime import datetime
from cpact.result_builder.result_builder import ResultCollector
from cpact.utils.scenario_parser import load_yaml_file
from cpact.core.context import Context
from cpact.utils.path_resolver import resolve_paths_in_yaml
import ocptv.output as tv
from concurrent.futures import ThreadPoolExecutor


class ScenarioInvoker:
    parent_scenario=""
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

        from cpact.core.scenario_runner import (
            ScenarioRunner,
        )  # Delayed import to avoid circular import
        scenario_output = {}
        scenario_path = self.step.get("scenario_path")
        if not scenario_path:
            raise ValueError("Scenario path is required for ScenarioInvoker step.")
        scenario_data = load_yaml_file(scenario_path)
        scenario_data, _ = resolve_paths_in_yaml(
            scenario_data["test_scenario"], scenario_data.get("paths", {})
        )
        parent_scenario = f"{self.context.get('scenario_parent')}.{scenario_data.get('test_name')}"
        start_time = time.time()
        self.context.set("scenario_parent", parent_scenario)
        runner = ScenarioRunner(
            scenario_data,
            self.context,
            thread_executor=self.thread_executor,
            validate_continue=self.validate_continue,
        )
        output, status, message = runner.run()

        end_time = time.time()
        duration = end_time - start_time
        start_timestamp = datetime.fromtimestamp(start_time).strftime("%Y-%m-%d %H:%M:%S")
        end_timestamp = datetime.fromtimestamp(end_time).strftime("%Y-%m-%d %H:%M:%S")

        # Convert duration to HH:MM:SS
        formatted_duration = time.strftime("%H:%M:%S", time.gmtime(duration))

        scenario_output = {
            "status": "PASS" if status else "FAIL",
            "start_timestamp": start_timestamp,
            "end_timestamp": end_timestamp,
            "duration": formatted_duration,
        }
        ResultCollector.get_instance().add_scenario_output(
            scenario_name=parent_scenario,
            scenario_output=scenario_output,
            headers={
                "test_id": scenario_data.get("test_id", ""),
                "test_name": scenario_data.get("test_name", ""),
                "test_group": scenario_data.get("test_group", ""),
                "tags": scenario_data.get("tags", ""),
                "description": scenario_data.get("description", ""),
                "map_file": scenario_data.get("map_file", ""),
                "scenario_path": scenario_path,
            }
        )
        return output, status, message
