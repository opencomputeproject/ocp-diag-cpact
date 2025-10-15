"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

===========================================================================
ScenarioRunner is the orchestration class responsible for executing a complete test scenario
composed of multiple steps. It manages lifecycle events, logging, diagnostics, and integrates
with OCP Test Validation (OCP TV) for structured output and reporting.

Features:
- Executes test steps sequentially using StepExecutor.
- Evaluates entry criteria and handles conditional step execution.
- Supports threaded execution for continued steps.
- Integrates with OCP TV for structured test run and step reporting.
- Logs step-level and scenario-level diagnostics and verdicts.
- Tracks execution status and handles failure propagation.

Classes:
    ScenarioRunner:
        Manages the execution of a test scenario and its steps.

Usage:
    Instantiate ScenarioRunner with a scenario dictionary, shared context, and optional thread pool.
    Call `run()` to execute the scenario and collect results.
    Automatically logs structured output and verdicts via OCP TV.
===========================================================================
"""
from concurrent.futures import ThreadPoolExecutor
from core.context import Context
from core.step_executor import StepExecutor
from utils.logger_utils import TestLogger
from utils.logger_utils import OCPTVFileWriter
import ocptv.output as tv
from ocptv.output import (
    DiagnosisType,
    LogSeverity,
    SoftwareType,
    TestResult,
    TestStatus,
)


class ScenarioRunner:
    def __init__(
        self,
        scenario: dict,
        context: Context,
        thread_executor: ThreadPoolExecutor = None,
        validate_continue: bool = False,
    ) -> None:
        """
        Initializes the ScenarioRunner with a scenario, context, and optional thread executor for continued steps.
        Args:
            scenario (dict): The test scenario to be executed.
            context (Context): The shared context for storing and managing data.
            thread_executor (ThreadPoolExecutor): Optional thread pool executor for handling continued steps.
            validate_continue (bool): Flag to indicate if continued steps should be validated.
        Returns:
            None
        """
        self.logger = TestLogger().get_logger()
        self.scenario = scenario
        self.context = context
        self.executor_continue = thread_executor or ThreadPoolExecutor(max_workers=5)
        self.validate_continue = validate_continue

    def run(self) -> tuple[None, bool, str]:
        """
        Runs the test scenario by executing the defined test steps and managing the test run lifecycle.
        Args:
            None
        Returns:
            tuple: A tuple containing None, a boolean indicating success or failure, and a message.
        """
        self.ocptv_writer = OCPTVFileWriter(
            TestLogger(), self.scenario.get("test_name")
        )

        # Configure OCP TV to use our custom writer
        tv.config(writer=self.ocptv_writer, enable_runtime_checks=True)
        self.logger.info(f"Running scenario: {self.scenario.get('test_name')}")
        data = self.scenario
        steps = data.get("test_steps", [])
        self.context.set("test_id", data.get("test_id"))
        run = tv.TestRun(name=self.scenario.get("test_name"), version="1.0")
        dut = tv.Dut(id=self.scenario["test_id"], name=self.scenario["test_name"])
        run.start(dut=dut)
        run.add_log(
            message=f"Running Test Scenario: {self.scenario.get('test_name')}",
            severity=LogSeverity.INFO,
        )
        run_status = True
        for step in steps:
            scenario_step = run.add_step(
                name=f"Step: ID:{step.get('step_id', 'Unnamed Step')}_{step.get('step_name', 'Unnamed Step')}"
            )
            scenario_step.__setattr__("step_details", step)
            with scenario_step.scope():
                executor = StepExecutor(
                    data.get("test_id"),
                    scenario_step,
                    self.context,
                    executor=self.executor_continue,
                )
                output, status, message = executor.run(
                    validate_continue=self.validate_continue
                )
                if not status:
                    self.logger.error(
                        f"Step '{step.get('step_name')}' failed: {message}"
                    )
                    scenario_step.add_diagnosis(
                        diagnosis_type=DiagnosisType.FAIL,
                        message=message,
                        verdict="failed",
                    )
                    # if not step.get("continue", False):
                    run_status = False
                    break
                else:
                    scenario_step.add_diagnosis(
                        diagnosis_type=DiagnosisType.PASS,
                        message=message,
                        verdict="passed",
                    )
                    self.logger.info(
                        f"Step '{step.get('step_name')}' completed successfully."
                    )

        if not run_status:
            run.add_log(
                severity=LogSeverity.ERROR,
                message=f"Scenario '{self.scenario.get('test_name')}' encountered errors.",
            )
            run.end(status=TestStatus.ERROR, result=TestResult.FAIL)
            return None, False, f"Step execution failed: {message}"
        else:
            run.add_log(
                severity=LogSeverity.INFO,
                message=f"Scenario '{self.scenario.get('test_name')}' completed successfully.",
            )
            run.end(status=TestStatus.COMPLETE, result=TestResult.PASS)
            return None, True, "Scenario executed successfully."
