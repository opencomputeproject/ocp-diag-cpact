"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.
"""

import time

from executor.command_executor import CommandExecutor
from executor.log_analyzer import LogAnalyzer
from executor.scenario_invoker import ScenarioInvoker
from executor.executor_factory import ExecutorFactory
from utils.logger_utils import TestLogger
from result_builder.result_builder import ResultCollector
from expression.evaluator import ExpressionEvaluator

class StepExecutor:
    def __init__(self, scenario_id, step, context, executor=None):
        self.logger = TestLogger().get_logger()
        self.step = step
        self.context = context
        self.evaluator = ExpressionEvaluator(context)
        self.scenario_id = scenario_id
        self.thread_executor = executor

    def run(self,  validate_continue=False):
        entry_criteria = self.step.get("entry_criteria")
        test_id = self.context.get("test_id")
        diagnostic_keys = self.context.get_diagnostic_context().get("keys", {}).get(test_id, {})
        if entry_criteria and not self.evaluator.evaluate(entry_criteria, diagnostic_keys):
            self.logger.info(f"[SKIP] Entry criteria '{entry_criteria}' not met. Skipping step. {diagnostic_keys}")
            ResultCollector().get_instance().add_step_result(
                self.scenario_id,
                step_id=self.step["step_id"],
                step_name=self.step["step_name"],
                step_type=self.step["step_type"],
                status="skip",
                duration=0,
                message="Entry criteria not met",
                details={
                    "entry_criteria": entry_criteria,
                    "keys": diagnostic_keys
                }
            )
            return None, True, "Entry criteria not met"

        loop = self.step.get("loop", 1)
        duration = self.step.get("duration")  # in seconds
        start_time = time.time()
        self.context.set("start_time", start_time)
        attempts = 0
        output, status, message = "", True, "Step executed successfully"
        while attempts < loop:
            try:
                output, status, message = self._execute_step(validate_continue=validate_continue)
                if not status:
                    self.logger.error(f"Step failed: {message}")
                    break  # Exit loop if step fails and continue is not set
                break
            except Exception as e:
                self.logger.warning(f"[Attempt {attempts + 1}] Step failed: {e}")
                if duration and (time.time() - start_time > duration):
                    self.logger.error(f"[TIMEOUT] Step did not complete within {duration} seconds.")
                    return None, False, f"Step timed out after {duration} seconds"
                time.sleep(1)  # backoff
                attempts += 1
                
        return output, status, message

    def _execute_step(self, validate_continue=False):
        test_id = self.context.get("test_id")
        executor_cls = ExecutorFactory.get_executor(self.step["step_type"])
        executor = executor_cls(self.step, self.context, self.thread_executor, validate_continue=validate_continue)
        output, status, message = executor.execute()
        if not validate_continue:
            ResultCollector().get_instance().add_step_result(
                self.scenario_id,
                step_id=self.step["step_id"],
                step_name=self.step["step_name"],
                step_type=self.step["step_type"],
                status="success" if status else "fail",
                duration=time.time() - self.context.get("start_time"),
                message=message
            )
        return output, status, message