"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

===========================================================================
Context is a singleton-based utility class that provides centralized storage and management
of shared data, diagnostic context, diagnostic codes, and continued step tracking across
test scenarios. It enables consistent access to scenario metadata and execution state.

Features:
- Stores global key-value pairs for scenario execution.
- Tracks diagnostic context keys and values per test case and step.
- Maintains diagnostic codes and their matches for reporting.
- Manages continued steps for asynchronous or deferred execution.
- Provides methods to update, retrieve, and validate context data.

Classes:
    Context:
        Singleton class for managing shared execution state and diagnostics.

Usage:
    Use `Context.get_instance()` to retrieve the singleton.
    Call `set()` and `get()` to manage global scenario data.
    Use `add_continued_step()` and `mark_validated()` to manage deferred steps.
    Use `update_diagnostic_context()` and `add_diagnostic_code()` to track diagnostics.
===========================================================================
"""

from typing import Any, Type, List


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

    _instance = None # Singleton instance

    def __init__(self):
        self.data = {}
        self.diagnostic_context = {}  # TC-wise keys-to-set
        self.diagnostic_codes = {}
        self.continued_steps = {}
        self.parameters_to_set = {}

    @classmethod
    def get_instance(cls: Type["Context"]) -> "Context":
        """
        Returns the singleton instance of the Context class.
        If the instance does not exist, it creates one.
        Args:
            cls (Any): The class type, used for accessing class-level attributes.

        Returns:
            Context: The singleton instance of the Context class.
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def set(self, key: str, value: Any) -> None:
        """
        Sets a value for a given key in the data store.
        Args:
            key (str): The key under which the value will be stored.
            value (Any): The value to be stored.
        Returns:
            None
        """
        self.data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """
        Retrieves the value for a given key from the data store.
        Args:
            key (str): The key whose value is to be retrieved.
            default (Any): The default value to return if the key does not exist.
        Returns:
            Any: The value associated with the key, or the default value if the key is not found.
        """
        return self.data.get(key, default)

    def get_all(self) -> dict:
        """
        Returns all stored data.
        Args:
            None
        Returns:
            dict: A dictionary containing all key-value pairs in the data store.
        """
        return self.data

    def add_continued_step(
        self, scenario_id: str, step_id: str, step_info: dict
    ) -> None:
        """
        Adds a continued step for a scenario.
        Args:
            scenario_id (str): The identifier for the scenario.
            step_id (str): The identifier for the step.
            step_info (dict): A dictionary containing information about the step.
        Returns:
            None
        """
        if scenario_id not in self.continued_steps:
            self.continued_steps[scenario_id] = {}
        self.continued_steps[scenario_id][step_id] = step_info

    def update_continue_step(
        self, scenario_id: str, step_id: str, step_info: dict
    ) -> None:
        """
        Updates information for a continued step.
        Args:
            scenario_id (str): The identifier for the scenario.
            step_id (str): The identifier for the step.
            step_info (dict): A dictionary containing updated information about the step.
        Returns:
            None
        """
        if (
            scenario_id in self.continued_steps
            and step_id in self.continued_steps[scenario_id]
        ):
            self.continued_steps[scenario_id][step_id].update(step_info)
        else:
            self.add_continued_step(scenario_id, step_id, step_info)

    def mark_validated(self, scenario_id: str, step_id: str) -> None:
        """
        Marks a continued step as validated.
        Args:
            scenario_id (str): The identifier for the scenario.
            step_id (str): The identifier for the step.
        Returns:
            None
        """
        if (
            scenario_id in self.continued_steps
            and step_id in self.continued_steps[scenario_id]
        ):
            self.continued_steps[scenario_id][step_id]["validated"] = True

    def update_diagnostic_context(
        self, tc_id: str, step_id: str, key: str, value: Any
    ) -> None:
        """
        Updates diagnostic context for a test case.
        Args:
            tc_id (str): The test case identifier.
            step_id (str): The step identifier.
            key (str): The diagnostic context key to be updated.
            value (Any): The value to be set for the diagnostic context key.
        Returns:
            None
        """
        if "keys" not in self.diagnostic_context:
            self.diagnostic_context["keys"] = {}
        if tc_id not in self.diagnostic_context["keys"]:
            self.diagnostic_context["keys"][tc_id] = {}
        if step_id not in self.diagnostic_context["keys"][tc_id]:
            self.diagnostic_context["keys"][tc_id][step_id] = {}
        self.diagnostic_context["keys"][tc_id][step_id][key] = value
        self.parameters_to_set[key] = value

    def add_diagnostic_code(self, tc_id: str, step_id: str, codes: List[Any]) -> None:
        """
        Adds a diagnostic code and its match for a test case.
        Args:
            tc_id (str): The test case identifier.
            step_id (str): The step identifier.
            codes (list): A list of diagnostic codes to be added.
        Returns:
            None
        """
        if "diag_code" not in self.diagnostic_codes:
            self.diagnostic_codes["diag_code"] = {}
        if tc_id not in self.diagnostic_codes["diag_code"]:
            self.diagnostic_codes["diag_code"][tc_id] = {}
        if step_id not in self.diagnostic_codes["diag_code"][tc_id]:
            self.diagnostic_codes["diag_code"][tc_id][step_id] = []
        self.diagnostic_codes["diag_code"][tc_id][step_id].extend(codes)

    def get_diagnostic_context(self) -> dict:
        """
        Retrieves the diagnostic context.
        Returns:
            dict: A dictionary containing the diagnostic context.
        """
        return self.diagnostic_context
    
    def get_parameters_to_set(self) -> dict:
        """
        Retrieves the diagnostic context.
        Returns:
            dict: A dictionary containing the diagnostic context.
        """
        return self.parameters_to_set

    def get_diagnostic_codes(self) -> dict:
        """
        Retrieves the diagnostic codes.
        Returns:
            dict: A dictionary containing the diagnostic codes.
        """
        return self.diagnostic_codes
