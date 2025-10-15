"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

===========================================================================
StepExecutor is a core orchestration class responsible for executing individual test steps
within a scenario. It manages entry criteria evaluation, step execution, diagnostics, and
result collection, integrating with multiple executor types and shared context.

Features:
- Evaluates entry criteria expressions using diagnostic keys.
- Executes steps using dynamic executor classes based on step type.
- Supports looped execution and duration-based retries.
- Collects step results and diagnostic verdicts.
- Integrates with ExpressionEvaluator, ResultCollector, and Orchestrator components.
- Supports threaded execution for continued steps.

Classes:
    StepExecutor:
        Manages the lifecycle of a single test step, including validation, execution, and reporting.

Usage:
    Instantiate StepExecutor with scenario ID, step object, context, and optional thread pool.
    Call `run(validate_continue=True)` to execute the step and collect results.
    Automatically logs outcomes and updates diagnostic and result tracking.
===========================================================================
"""
import time

from executor.command_executor import CommandExecutor
from concurrent.futures import ThreadPoolExecutor
from core.context import Context
from executor.log_analyzer import LogAnalyzer
from executor.scenario_invoker import ScenarioInvoker
from executor.executor_factory import ExecutorFactory
from utils.logger_utils import TestLogger
from result_builder.result_builder import ResultCollector
from expression.evaluator import ExpressionEvaluator
from ocptv.output import (
    DiagnosisType,
    LogSeverity,
    SoftwareType,
    TestResult,
    TestStatus,
)
import ocptv.output as tv


class StepExecutor:
    def __init__(
        self,
        scenario_id: str,
        scenario_step: tv.step,
        context: Context,
        executor: ThreadPoolExecutor = None,
    ) -> None:
        """
        Initializes the StepExecutor with a scenario step, context, and optional thread executor for continued steps.
        Args:
            scenario_id (str): The identifier for the scenario.
            scenario_step (tv.step): The test step to be executed.
            context (Context): The shared context for storing and managing data.
            executor (ThreadPoolExecutor): Optional thread pool executor for handling continued steps.
        Returns:
            None
        """
        self.logger = TestLogger().get_logger()
        self.step_details = scenario_step.step_details
        self.scenario_step = scenario_step
        self.context = context
        self.evaluator = ExpressionEvaluator(context)
        self.scenario_id = scenario_id
        self.thread_executor = executor

    def run(self, validate_continue: bool = False) -> tuple[str, bool, str]:
        """
        Runs the test step by executing the defined action and managing the step lifecycle.
        Args:
            validate_continue (bool): Flag to indicate if continued steps should be validated.
        Returns:
            tuple: A tuple containing the output, a boolean indicating success or failure, and a message.
        """
        entry_criteria = self.step_details.get("entry_criteria")
        test_id = self.context.get("test_id")
        diagnostic_keys = (
            self.context.get_parameters_to_set()
        )
        if entry_criteria and not self.evaluator.evaluate(
            entry_criteria, diagnostic_keys
        ):
            self.logger.info(
                f"[SKIP] Entry criteria '{entry_criteria}' not met. Skipping step. {diagnostic_keys}"
            )
            ResultCollector().get_instance().add_step_result(
                self.scenario_id,
                step_id=self.step_details["step_id"],
                step_name=self.step_details["step_name"],
                step_type=self.step_details["step_type"],
                status="skip",
                duration=0,
                message="Entry criteria not met",
                details={"entry_criteria": entry_criteria, "keys": diagnostic_keys},
            )
            self.scenario_step.add_diagnosis(
                diagnosis_type=DiagnosisType.UNKNOWN,
                message="Entry criteria not met",
                verdict="skipped",
            )
            return None, True, "Entry criteria not met"

        loop = self.step_details.get("loop", 1)
        duration = self.step_details.get("duration")  # in seconds
        start_time = time.time()
        self.context.set("start_time", start_time)
        attempts = 0
        output, status, message = "", True, "Step executed successfully"
        while attempts < loop:
            try:
                output, status, message = self._execute_step(
                    validate_continue=validate_continue
                )
                if not status:
                    self.logger.error(f"Step failed: {message}")
                    self.scenario_step.add_diagnosis(
                        diagnosis_type=DiagnosisType.FAIL,
                        message=message,
                        verdict="failed",
                    )
                    break  # Exit loop if step fails and continue is not set
                break
            except Exception as e:
                self.scenario_step.add_log(
                    LogSeverity.WARNING, f"[Attempt {attempts + 1}] Step failed: {e}"
                )
                self.logger.warning(f"[Attempt {attempts + 1}] Step failed: {e}")
                if duration and (time.time() - start_time > duration):
                    self.scenario_step.add_log(
                        LogSeverity.ERROR,
                        f"[TIMEOUT] Step did not complete within {duration} seconds.",
                    )
                    self.logger.error(
                        f"[TIMEOUT] Step did not complete within {duration} seconds."
                    )
                    return None, False, f"Step timed out after {duration} seconds"
                time.sleep(1)  # backoff
                attempts += 1

        return output, status, message

    def _execute_step(self, validate_continue: bool) -> tuple[str, bool, str]:
        """
        Executes the test step using the appropriate executor based on the step type.
        Args:
            validate_continue (bool): Flag to indicate if continued steps should be validated.
        Returns:
            tuple: A tuple containing the output, a boolean indicating success or failure, and a message.
        """
        test_id = self.context.get("test_id")
        executor_cls = ExecutorFactory.get_executor(self.step_details["step_type"])
        executor = executor_cls(
            self.scenario_step,
            self.context,
            self.thread_executor,
            validate_continue=validate_continue,
        )
        output, status, message = executor.execute()
        if not validate_continue:
            ResultCollector().get_instance().add_step_result(
                self.scenario_id,
                step_id=self.step_details["step_id"],
                step_name=self.step_details["step_name"],
                step_type=self.step_details["step_type"],
                status="success" if status else "fail",
                duration=time.time() - self.context.get("start_time"),
                message=message,
            )
            self.scenario_step.add_diagnosis(
                diagnosis_type=DiagnosisType.FAIL if not status else DiagnosisType.PASS,
                message=message,
                verdict="passed" if status else "failed",
            )
        return output, status, message
