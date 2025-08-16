"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.
"""

import re
import time

from core.context import Context
from core.scenario_runner import ScenarioRunner
from core.step_executor import StepExecutor

from concurrent.futures import ThreadPoolExecutor
from result_builder.result_builder import ResultCollector

from utils.logger_utils import TestLogger
from utils.docker_executor import DockerExecutor

class Orchestrator:
    def __init__(self):
        self.logger = TestLogger().get_logger()
        self.context = Context.get_instance()
        self.executor_continue = ThreadPoolExecutor(max_workers=5)

    def run(self, test_scenario):
        # self.logger.info(f"Starting test scenario: {yaml_path}")
        # scenario = load_yaml(yaml_path)
        self._build_metadata(test_scenario)
        docker_steps = test_scenario.get("docker", [])
        if docker_steps:
            self.load_dockers(test_scenario)
        self._run_steps(test_scenario)

    def _build_metadata(self, scenario):
        self.context.set("test_id", scenario.get("test_id"))
        self.context.set("test_name", scenario.get("test_name"))
        self.context.set("test_group", scenario.get("test_group"))
        self.logger.info(f"Test Metadata set: ID={scenario.get('test_id')}")

    def load_dockers(self, scenario):
        """
        Load Docker containers as specified in the scenario.
        """
        docker_steps = scenario.get("docker", [])
        if not docker_steps:
            self.logger.info("No Docker steps found in scenario.")
            return
        
        for step_index, step_data in enumerate(docker_steps):
            self.logger.info(f"Loading Docker step {step_index + 1}/{len(docker_steps)}: {step_data.get('container_name', 'Unnamed')}")
            docker_executor = DockerExecutor(step_data, step_index)
            docker_executor.load_docker()
            if "docker_steps" not in self.context.get_all():
                self.context.set("docker_steps", {})
            self.context.get("docker_steps")[step_data.get("container_name")] = docker_executor

        self.logger.info("All Docker containers loaded successfully.")
    
    def _run_steps(self, scenario):
        steps = scenario.get("test_steps")
        self.logger.info(f"Running {len(steps)} steps in scenario: {scenario.get('test_name')}")
        if steps:
            self.logger.info(f"Running inline steps...")
            for step in steps:
                start_time = time.time()
                self.context.set("start_time", start_time)
                self.logger.info(f"Executing step: {step.get('step_name', 'Unnamed Step')}")
                output, status, message = StepExecutor(scenario.get("test_id"), step, self.context, executor=self.executor_continue).run()
                if not status:
                    self.logger.error(f"Step failed: {message}")
                    # if not step.get("continue", False):
                    break
                        # raise Exception(f"Step execution failed: {message}")
                
        else:
            self.logger.info("Delegating to ScenarioRunner...")
            ScenarioRunner(scenario=scenario, context=self.context).run()
        
        
        self.logger.info("Finalizing continued steps...")
        final_results = self.finalize_all_continued_steps(self.context)
        if not final_results:
            self.logger.info("No continued steps to finalize.")
        else:
            for step_id, result in final_results.items():
                if result["status"] == "error":
                    self.logger.error(f"[{step_id}] failed: {result['error']}")
                else:
                    self.logger.info(f"[{step_id}] completed. Output snippet: {result['output'][:100]}")
            self.logger.info("All continued steps finalized.")
        self.executor_continue.shutdown(wait=True)
        if self.context.get("docker_steps"):
            self.logger.info("Stopping all Docker containers...")
            for docker_executor in self.context.get("docker_steps").values():
                docker_executor.stop_container()
            self.logger.info("All Docker containers stopped.")

    def finalize_all_continued_steps(self, context):
        results = {}
        self.logger.debug(f"Finalizing continued steps in context: {context.continued_steps}")
        for scenario_id, scenario_info in context.continued_steps.items():
            
            for step_id, info in scenario_info.items():
                self.logger.info(f"Finalizing continued step: {scenario_id}, {step_id}")
                if info.get("validated"):
                    self.logger.info(f"Step {scenario_id} {step_id} already validated. Skipping.")
                    continue  # Skip already validated ones
                
                future = info.get("future")
                continue_step = info.get("step")
                if not continue_step:
                    self.logger.warning(f"No step found for continued step {scenario_id} {step_id}. Skipping.")
                    continue
                conn_type = continue_step.get("connection_type", "local")
                self.logger.info(f"Connection type for step {scenario_id} {step_id}: {conn_type}")
                # self._build_metadata(scenario_info)
                self.context.set("scenario_id", scenario_id)
                output, status, message = StepExecutor(scenario_id, continue_step, self.context, executor=self.executor_continue).run(validate_continue=True)
                if not status:
                    self.logger.error(f"Continued step failed: {message}")
                results[scenario_id] = {
                    "output": output,
                    "status": "error" if not status else "success",
                    "error": message if not status else None
                }
        return results
