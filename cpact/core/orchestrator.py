"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

===========================================================================
Orchestrator is the central controller for executing YAML-based test scenarios. It manages
metadata setup, Docker container lifecycle, step execution, and finalization of continued steps.
It integrates with OCP TV for structured test reporting and supports threaded execution.

Features:
- Initializes and runs test scenarios with step-by-step orchestration.
- Loads and manages Docker containers defined in the scenario.
- Executes inline steps and delegates to ScenarioRunner when needed.
- Finalizes continued steps and collects their results.
- Integrates with OCP TV for structured logging, diagnostics, and verdicts.
- Supports context propagation and thread-based execution for parallel steps.

Classes:
    Orchestrator:
        Manages the full lifecycle of a test scenario including setup, execution, and teardown.

Usage:
    Instantiate Orchestrator and call `run(test_scenario)` with a parsed scenario dictionary.
    Automatically handles Docker setup, step execution, and result collection.
    Finalizes continued steps and stops containers after execution.
===========================================================================
"""

import re
import time
from typing import Any, Type, List

from core.context import Context
from core.scenario_runner import ScenarioRunner
from core.step_executor import StepExecutor

from concurrent.futures import ThreadPoolExecutor
from result_builder.result_builder import ResultCollector

from utils.logger_utils import TestLogger
from utils.docker_executor import DockerExecutor
from utils.logger_utils import OCPTVFileWriter
import ocptv.output as tv
from ocptv.output import (
    DiagnosisType,
    LogSeverity,
    SoftwareType,
    TestResult,
    TestStatus,
)


class Orchestrator:
    def __init__(self) -> None:
        """
        Initializes the Orchestrator with a logger, context, and a thread pool executor for continued
        steps.
        Args:
            self: The instance of the Orchestrator class.
        Returns:
            None
        """
        self.logger = TestLogger().get_logger()
        self.context = Context.get_instance()
        self.executor_continue = ThreadPoolExecutor(max_workers=5)

    def run(self, test_scenario: dict = None) -> None:
        """
        Runs the test scenario by loading Docker containers if specified, building metadata,
        and executing the defined test steps.
        Args:
            test_scenario (dict): The test scenario configuration.
        Returns:
            None"""
        # self.logger.info(f"Starting test scenario: {yaml_path}")
        # scenario = load_yaml(yaml_path)
        self.ocptv_writer = OCPTVFileWriter(
            TestLogger(), test_scenario.get("test_name")
        )

        # Configure OCP TV to use our custom writer
        tv.config(writer=self.ocptv_writer, enable_runtime_checks=True)

        self._build_metadata(test_scenario)
        docker_steps = test_scenario.get("docker", [])
        if docker_steps:
            self.load_dockers(test_scenario)
        self._run_steps(test_scenario)

    def _build_metadata(self, scenario: dict = None) -> None:
        """
        Builds and sets metadata in the context based on the provided scenario.
        Args:
            scenario (dict): The test scenario configuration.
        Returns:
            None
        """
        self.context.set("test_id", scenario.get("test_id"))
        self.context.set("test_name", scenario.get("test_name"))
        self.context.set("test_group", scenario.get("test_group"))
        self.logger.info(f"Test Metadata set: ID={scenario.get('test_id')}")

    def load_dockers(self, scenario: dict = None) -> None:
        """
        Loads Docker containers specified in the scenario and updates the context with the
        Docker executors.
        Args:
            scenario (dict): The test scenario configuration.
        Returns:
            None
        """
        docker_steps = scenario.get("docker", [])
        if not docker_steps:
            self.logger.info("No Docker steps found in scenario.")
            return

        for step_index, step_data in enumerate(docker_steps):
            self.logger.info(
                f"Loading Docker step {step_index + 1}/{len(docker_steps)}: {step_data.get('container_name', 'Unnamed')}"
            )
            docker_executor = DockerExecutor(step_data, step_index)
            docker_executor.load_docker()
            if "docker_steps" not in self.context.get_all():
                self.context.set("docker_steps", {})
            self.context.get("docker_steps")[
                step_data.get("container_name")
            ] = docker_executor

        self.logger.info("All Docker containers loaded successfully.")

    def _run_steps(self, scenario: dict = None) -> None:
        """
        Runs the test steps defined in the scenario, handling both inline and continued steps.
        Args:
            scenario (dict): The test scenario configuration.
        Returns:
            None
        """
        steps = scenario.get("test_steps")
        self.logger.info(
            f"Running {len(steps)} steps in scenario: {scenario.get('test_name')}"
        )
        if steps:
            self.logger.info(f"Running inline steps...")
            run = tv.TestRun(name=scenario.get("test_name"), version="1.0")
            dut = tv.Dut(id=scenario["test_id"], name=scenario["test_name"])
            run.start(dut=dut)
            run.add_log(
                message=f"Running Test Scenario: {scenario.get('test_name')}",
                severity=LogSeverity.INFO,
            )
            run_status = True
            for step in steps:
                scenario_step = run.add_step(
                    name=f"Step: ID:{step.get('step_id', 'Unnamed Step')}_{step.get('step_name', 'Unnamed Step')}"
                )
                scenario_step.__setattr__("step_details", step)

                with scenario_step.scope():
                    start_time = time.time()
                    self.context.set("start_time", start_time)
                    self.logger.info(
                        f"Executing step: {step.get('step_name', 'Unnamed Step')}"
                    )
                    output, status, message = StepExecutor(
                        scenario.get("test_id"),
                        scenario_step,
                        self.context,
                        executor=self.executor_continue,
                    ).run()
                    if not status:
                        self.logger.error(f"Step failed: {message}")
                        scenario_step.add_diagnosis(
                            diagnosis_type=DiagnosisType.FAIL,
                            message=message,
                            verdict="failed",
                        )

                        # if not step.get("continue", False):
                        run_status = False
                        break
                        # raise Exception(f"Step execution failed: {message}")
                    scenario_step.add_diagnosis(
                        diagnosis_type=DiagnosisType.PASS,
                        message=message,
                        verdict="passed",
                    )

        else:
            self.logger.info("Delegating to ScenarioRunner...")
            ScenarioRunner(scenario=scenario, context=self.context).run()

        if not run_status:
            run.end(status=TestStatus.ERROR, result=TestResult.FAIL)
        else:
            run.end(status=TestStatus.COMPLETE, result=TestResult.PASS)

        self.logger.info("Finalizing continued steps...")
        final_results = self.finalize_all_continued_steps(self.context)
        if not final_results:
            self.logger.info("No continued steps to finalize.")
        else:
            for step_id, result in final_results.items():
                if result["status"] == "error":
                    self.logger.error(f"[{step_id}] failed: {result['error']}")
                else:
                    self.logger.info(
                        f"[{step_id}] completed. Output snippet: {result['output'][:100]}"
                    )
            self.logger.info("All continued steps finalized.")
        self.executor_continue.shutdown(wait=True)
        if self.context.get("docker_steps"):
            self.logger.info("Stopping all Docker containers...")
            for docker_executor in self.context.get("docker_steps").values():
                docker_executor.stop_container()
            self.logger.info("All Docker containers stopped.")

    def finalize_all_continued_steps(self, context: Context) -> dict:
        """
        Finalizes all continued steps by executing them and collecting their results.
        Args:
            context (Context): The context containing continued steps information.
        Returns:
            dict: A dictionary containing the results of all finalized continued steps.
        """
        results = {}
        self.logger.debug(
            f"Finalizing continued steps in context: {context.continued_steps}"
        )
        for scenario_id, scenario_info in context.continued_steps.items():

            for step_id, info in scenario_info.items():
                self.logger.info(f"Finalizing continued step: {scenario_id}, {step_id}")
                if info.get("validated"):
                    self.logger.info(
                        f"Step {scenario_id} {step_id} already validated. Skipping."
                    )
                    continue  # Skip already validated ones

                future = info.get("future")
                scenario_step = info.get("step")
                continue_step = (
                    scenario_step.step_details if scenario_step else info.get("step")
                )
                if not continue_step:
                    self.logger.warning(
                        f"No step found for continued step {scenario_id} {step_id}. Skipping."
                    )
                    continue
                conn_type = continue_step.get("connection_type", "local")
                self.logger.info(
                    f"Connection type for step {scenario_id} {step_id}: {conn_type}"
                )
                # self._build_metadata(scenario_info)
                self.context.set("scenario_id", scenario_id)
                output, status, message = StepExecutor(
                    scenario_id,
                    scenario_step,
                    self.context,
                    executor=self.executor_continue,
                ).run(validate_continue=True)
                if not status:
                    self.logger.error(f"Continued step failed: {message}")
                results[scenario_id] = {
                    "output": output,
                    "status": "error" if not status else "success",
                    "error": message if not status else None,
                }
        return results
