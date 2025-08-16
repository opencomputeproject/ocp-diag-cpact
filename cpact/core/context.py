"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.
"""

from typing import Any

class Context:
    """
    Context is a singleton class that provides a centralized storage and management system for shared data, diagnostic contexts, diagnostic codes, and continued steps within the application.
    Attributes:
        data (dict): General-purpose key-value store for application-wide data.
        diagnostic_context (dict): Stores test case-wise diagnostic context keys and their associated values.
        diagnostic_codes (dict): Maintains diagnostic codes and their matches for each test case.
        continued_steps (dict): Tracks continued steps for scenarios, including step information and validation status.
    Methods:
        get_instance(): Returns the singleton instance of Context.
        set(key, value): Sets a value for a given key in the data store.
        get(key, default=None): Retrieves the value for a given key from the data store.
        get_all(): Returns all stored data.
        add_continued_step(scenario_id, step_id, step_info): Adds a continued step for a scenario.
        update_continue_step(scenario_id, step_id, step_info): Updates information for a continued step.
        mark_validated(scenario_id, step_id): Marks a continued step as validated.
        update_diagnostic_context(tc_id, key, value): Updates diagnostic context for a test case.
        add_diagnostic_code(tc_id, code, match): Adds a diagnostic code and its match for a test case.
        get_diagnostic_context(): Retrieves the diagnostic context.
        get_diagnostic_codes(): Retrieves the diagnostic codes.
    
    """
    
    _instance = None

    def __init__(self):
        self.data = {}
        self.diagnostic_context = {}      # TC-wise keys-to-set
        self.diagnostic_codes = {}
        self.continued_steps = {}

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def set(self, key, value):
        self.data[key] = value

    def get(self, key, default=None):
        return self.data.get(key, default)

    def get_all(self):
        return self.data
    
    def add_continued_step(self, scenario_id, step_id, step_info):
        if scenario_id not in self.continued_steps:
            self.continued_steps[scenario_id] = {}
        self.continued_steps[scenario_id][step_id] = step_info
        
    def update_continue_step(self, scenario_id, step_id, step_info):
        if scenario_id in self.continued_steps and step_id in self.continued_steps[scenario_id]:
            self.continued_steps[scenario_id][step_id].update(step_info)
        else:
            self.add_continued_step(scenario_id, step_id, step_info)

    def mark_validated(self, scenario_id, step_id):
        if scenario_id in self.continued_steps and step_id in self.continued_steps[scenario_id]:
            self.continued_steps[scenario_id][step_id]["validated"] = True
    
    def update_diagnostic_context(self, tc_id: str, key: str, value: Any):
        if "keys" not in self.diagnostic_context:
            self.diagnostic_context["keys"] = {}
        if tc_id not in self.diagnostic_context["keys"]:
            self.diagnostic_context["keys"][tc_id] = {}
        self.diagnostic_context["keys"][tc_id][key] = value

    def add_diagnostic_code(self, tc_id: str, code: str,  match: str):
        if "diag_code" not in self.diagnostic_codes:
            self.diagnostic_codes["diag_code"] = {}
        if tc_id not in self.diagnostic_codes["diag_code"]:
            self.diagnostic_codes["diag_code"][tc_id] = []
        self.diagnostic_codes["diag_code"][tc_id].append({
            "code": code,
            "match": match
        })

    def get_diagnostic_context(self):
        return self.diagnostic_context

    def get_diagnostic_codes(self):
        return self.diagnostic_codes
