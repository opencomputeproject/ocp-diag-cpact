"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.
"""

import copy
import threading
from time import time
from tabulate import tabulate

from utils.logger_utils import TestLogger


class ResultCollector:
    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self.reset()
        self.logger = TestLogger().get_logger()

    @classmethod
    def get_instance(cls):
        with cls._lock:
            if not cls._instance:
                cls._instance = cls()
        return cls._instance

    def reset(self):
        self.step_results = []         # Each step's result (status, duration, msg, etc.)
        self.keys_to_set = {}         # Key-value pairs from output analysis
        self.diagnostics = []          # All diagnostic matches
        self.diagnostics_codes = []  # Diagnostic codes collected
        self.step_index = {}           # Mapping: step_name -> index in step_results list

    def add_step_result(self, scenario_id, step_id, step_name, step_type, status, duration, message="", **kwargs):
        result = {
            "scenario_id": copy.deepcopy(scenario_id),
            "step_id": copy.deepcopy(step_id),
            "step_name": copy.deepcopy(step_name),
            "step_type": copy.deepcopy(step_type),
            "status": copy.deepcopy(status),
            "duration": round(copy.deepcopy(duration),3),
            "message": copy.deepcopy(message),
            # **kwargs
        }
        for k, v in kwargs.items():
            result[k] = copy.deepcopy(v)
        self.step_index[step_id] = len(self.step_results)
        self.step_results.append(result)

    def update_step_result(self, step_id, **kwargs):
        """
        Update fields for an existing step result (e.g., status, duration, message).
        """
        idx = self.step_index.get(step_id)
        if idx is not None:
            self.step_results[idx].update(kwargs)
        else:
            raise ValueError(f"No result found for step '{step_id}'")

    # def add_context_key(self, key, value):
    #     self.context_keys[key] = value

    def add_diagnostic(self, scenario_id, code, match_text, message=""):
        self.diagnostics.append({
            "scenario_id": scenario_id,
            "code": code,
            "message": message,
            "match": match_text
        })
        self.diagnostics_codes.append(code)

    def add_diagnostic_keys(self, tc_id, key, value):
        if tc_id not in self.keys_to_set:
            self.keys_to_set[tc_id] = {}
        self.keys_to_set[tc_id][key] = value

    def get_diagnostic_keys(self, tc_id):
        return self.keys_to_set.get(tc_id, {})
    
    def get_results(self):
        return {
            "diagnostic_codes": self.diagnostics_codes,
            "diagnostics": self.diagnostics,
            "keys": self.keys_to_set,
            "steps": self.step_results
        }

    def print_summary(self):
        self.logger.info("\n--- Test Summary ---")
        for r in self.step_results:
            status_icon = "[PASS]" if r["status"] == "PASS" else "[FAIL]"
            self.logger.info(f"{status_icon} Step: {r['step_name']} | Type: {r['step_type']} | Time: {r['duration']:.2f}s | Msg: {r.get('message', '')}")

        if self.diagnostics:
            self.logger.info("\n❌ Detected Diagnostic Issues:")
            for d in self.diagnostics:
                self.logger.info(f"Code: {d['code']} | Message: {d['message']} | Match: {d['match']}")
        if self.keys_to_set:
            self.logger.info("\n🔑 Final Context Keys:")
            for k, v in self.keys_to_set.items():
                self.logger.info(f"{k} = {v}")
    
    def print_summary_table(self):
        headers = ["Step Name", "Type", "Status", "Duration (s)", "Message"]
        table = []
        for r in self.step_results:
            table.append([
            r.get("step_name", ""),
            r.get("step_type", ""),
            r.get("status", ""),
            f"{r.get('duration', 0):.2f}",
            self.shorten_string(r.get("message", ""), max_length=50) if r.get("message") else ""
            ])
        self.logger.info("\n" + tabulate(table, headers=headers, tablefmt="grid"))


    def shorten_string(self, text, max_length=20):
        if len(text) > max_length:
            return text[:max_length - 3] + "..."
        return text

    def dump_results(self, file_path):
        """
        Save the collected results to a JSON file.
        """
        import json
        with open(file_path, 'w') as f:
            json.dump(self.get_results(), f, indent=4)
        self.logger.info(f"Results saved to {file_path}")
