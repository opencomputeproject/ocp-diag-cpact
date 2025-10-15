"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

===========================================================================
ResultCollector is a singleton-based utility class for aggregating and reporting test execution results.
It tracks step outcomes, diagnostics, context keys, and provides formatted summaries and exports for
scenario validation and analysis.

Features:
- Collects step-level results including status, duration, and messages.
- Tracks diagnostic codes and messages across test steps.
- Supports context key-value storage for output analysis.
- Provides tabular summaries of results and diagnostics.
- Filters and merges diagnostic entries for uniqueness.
- Exports results and diagnostics to JSON files.
- Prints formatted tables using tabulate for readability.

Classes:
    ResultCollector:
        Centralized result aggregation and reporting class.
        Designed for use across test execution workflows.

Usage:
    Use `ResultCollector.get_instance()` to retrieve the singleton.
    Call `add_step_result()` and `add_diagnostic()` to record results.
    Use `print_summary()` or `print_summary_table()` to display results.
    Use `dump_results()` or `dump_diagnostics()` to export data.
===========================================================================
"""
from collections import defaultdict
import copy
import json
import threading
from time import time
from tabulate import tabulate
import pprint
import pandas as pd
import textwrap
from typing import Any, Type, List
from utils.logger_utils import TestLogger


class ResultCollector:
    _instance = None # Singleton instance
    _lock = threading.Lock() # Lock for thread-safe singleton creation

    def __init__(self) -> None:
        """
        Initializes the ResultCollector singleton instance.
        Returns:
            None
        """
        self.reset()
        self.logger = TestLogger().get_logger()

    @classmethod
    def get_instance(cls: Type["ResultCollector"]) -> "ResultCollector":
        """
        Returns the singleton instance of ResultCollector.
        If the instance does not exist, it creates one in a thread-safe manner.
        Returns:
            ResultCollector: The singleton instance of ResultCollector.
        """
        with cls._lock:
            if not cls._instance:
                cls._instance = cls()
        return cls._instance

    def reset(self) -> None:
        """
        Resets the internal state of the ResultCollector.
        Returns:
            None
        """
        self.step_results = []  # Each step's result (status, duration, msg, etc.)
        self.keys_to_set = {}  # Key-value pairs from output analysis
        self.diagnostics = []  # All diagnostic matches
        self.diagnostics_codes = []  # Diagnostic codes collected
        self.step_index = {}  # Mapping: step_name -> index in step_results list

    def add_step_result(
        self,
        scenario_id: str,
        step_id: str,
        step_name: str,
        step_type: str,
        status: str,
        duration: float,
        message: str = "",
        **kwargs: dict,
    ) -> None:
        """
        Adds a result entry for a test step.
        Args:
            scenario_id (str): The identifier for the scenario.
            step_id (str): The identifier for the step.
            step_name (str): The name of the step.
            step_type (str): The type of the step.
            status (str): The status of the step (e.g., "pass", "fail", "skip").
            duration (float): The duration taken to execute the step in seconds.
            message (str): An optional message providing additional information about the step result.
            **kwargs (dict): Additional key-value pairs to include in the result entry.
        Returns:
            None
        """
        result = {
            "scenario_id": copy.deepcopy(scenario_id),
            "step_id": copy.deepcopy(step_id),
            "step_name": copy.deepcopy(step_name),
            "step_type": copy.deepcopy(step_type),
            "status": copy.deepcopy(status),
            "duration": round(copy.deepcopy(duration), 3),
            "message": copy.deepcopy(message),
            # **kwargs
        }
        for k, v in kwargs.items():
            result[k] = copy.deepcopy(v)
        self.step_index[step_id] = len(self.step_results)
        self.step_results.append(result)

    def update_step_result(self, step_id: str, **kwargs: dict) -> None:
        """
        Updates an existing step result entry with additional information.
        Args:
            step_id (str): The identifier for the step to be updated.
            **kwargs (dict): Key-value pairs to update in the existing result entry.
        Returns:
            None
        """
        idx = self.step_index.get(step_id)
        if idx is not None:
            self.step_results[idx].update(kwargs)
        else:
            raise ValueError(f"No result found for step '{step_id}'")

    # def add_context_key(self, key, value):
    #     self.context_keys[key] = value

    def add_diagnostic(
        self, scenario_id: str, step_id: str, codes: list[str], message: str = ""
    ) -> None:
        """
        Adds a diagnostic entry with associated codes and message.
        Args:
            scenario_id (str): The identifier for the scenario.
            step_id (str): The identifier for the step.
            codes (list): A list of diagnostic codes associated with the entry.
            message (str): An optional message providing additional information about the diagnostic entry.
        Returns:
            None
        """
        self.diagnostics.append(
            {
                "scenario_id": scenario_id,
                "step_id": step_id,
                "codes": codes,
                "message": message,
            }
        )
        self.diagnostics_codes.extend(codes)

    def add_diagnostic_keys(
        self, tc_id: str, step_id: str, key: str, value: object
    ) -> None:
        """
        Adds a diagnostic key-value pair for a specific test case and step.
        Args:
            tc_id (str): The test case identifier.
            step_id (str): The step identifier.
            key (str): The diagnostic context key to be added.
            value (Any): The value to be set for the diagnostic context key.
         Returns:
            None
        """
        if tc_id not in self.keys_to_set:
            self.keys_to_set[tc_id] = {}
        if step_id not in self.keys_to_set[tc_id]:
            self.keys_to_set[tc_id][step_id] = {}
        self.keys_to_set[tc_id][step_id][key] = value

    def get_diagnostic_keys(self, tc_id: str) -> dict:
        """
        Retrieves diagnostic keys for a specific test case.
        Args:
            tc_id (str): The test case identifier.
        Returns:
            dict: A dictionary containing the diagnostic keys for the specified test case.
        """
        return self.keys_to_set.get(tc_id, {})

    def get_results(self) -> dict:
        """
        Retrieves the collected results including diagnostics and keys.
        Returns:
            dict: A dictionary containing diagnostics, keys, and step results.
        """
        return {
            "diagnostic_codes": self.diagnostics_codes,
            "diagnostics": self.diagnostics,
            "keys": self.keys_to_set,
            "steps": self.step_results,
        }

    def print_summary(self) -> None:
        """
        Prints a summary of the collected results including step results and diagnostics.
        Returns:
            None
        """
        for r in self.step_results:
            status_icon = (
                "[PASS]"
                if r["status"] not in ["FAIL", "fail", "error", "ERROR"]
                else "[FAIL]"
            )
            self.logger.info(
                f"{status_icon} Step: {r['step_name']} | Type: {r['step_type']} | Time: {r['duration']:.2f}s | Msg: {r.get('message', '')}"
            )

        if self.diagnostics:
            self.logger.info("\n❌ Detected Diagnostic Issues:")

            filtered_data = self.filter_unique_diagnostics(self.diagnostics)
            self.diagnostic_table(filtered_data)
            self.diagnostic_summary()
        if self.keys_to_set:
            self.logger.info("\n🔑 Final Context Keys:")
            for k, v in self.keys_to_set.items():
                self.logger.info(f"{k} = {v}")

    def print_summary_table(self) -> None:
        """
        Prints a tabular summary of the step results.
        Returns:
            None
        """
        headers = ["Step Name", "Type", "Status", "Duration (s)", "Message"]
        table = []
        for r in self.step_results:
            table.append(
                [
                    r.get("step_name", ""),
                    r.get("step_type", ""),
                    r.get("status", ""),
                    f"{r.get('duration', 0):.2f}",
                    (
                        self.shorten_string(r.get("message", ""), max_length=50)
                        if r.get("message")
                        else ""
                    ),
                ]
            )
        self.logger.info("\n" + tabulate(table, headers=headers, tablefmt="grid"))

    def shorten_string(self, text: str, max_length: int = 20) -> str:
        """
        Shortens a string to a specified maximum length, adding ellipsis if truncated.
        Args:
            text (str): The string to be shortened.
            max_length (int): The maximum allowed length of the string.
        Returns:
            str: The shortened string.
        """
        if len(text) > max_length:
            return text[: max_length - 3] + "..."
        return text

    def dump_results(self, file_path: str) -> None:
        """
        Save the complete results to a JSON file.
        Args:
            file_path (str): The path to the file where results should be saved.
        Returns:
            None
        """
        import json

        with open(file_path, "w") as f:
            json.dump(self.get_results(), f, indent=4)
        self.logger.info(f"Results saved to {file_path}")

    def dump_diagnostics(self, file_path: str) -> None:
        """
        Save only the diagnostics to a JSON file.
        Args:
            file_path (str): The path to the file where diagnostics should be saved.
        Returns:
            None
        """
        import json

        data = self.filter_unique_diagnostics(self.diagnostics)
        with open(file_path, "w") as f:
            json.dump(data, f, indent=4)
        self.logger.info(f"Diagnostics saved to {file_path}")

    def diagnostic_table(self, diagnostic_data: dict) -> None:
        """
        Print a detailed table of diagnostic data.
        Args:
            diagnostic_data (dict): The diagnostic data to be displayed.
        Returns:
            None
        """
        rows = []
        all_columns = ["Diagnostic Code"]  # start with first column

        # Flatten data and dynamically track all column headers in insertion order
        for main_key, entries in diagnostic_data.items():
            for entry in entries:
                flat_entry = {"Diagnostic Code": main_key}
                # Only update if entry is a dict
                if isinstance(entry, dict):
                    if main_key in entry.values():
                        entry = {k: v for k, v in entry.items() if v != main_key}
                    flat_entry.update(entry)
                rows.append(flat_entry)
                # Add new keys to columns dynamically
                if isinstance(entry, dict):
                    for k in entry.keys():
                        if k not in all_columns:
                            all_columns.append(k)
        # Convert rows to consistent list for tabulate
        table_data = [
            [r.get(c, "") if r.get(c) is not None else "" for c in all_columns]
            for r in rows
        ]
        if table_data:
            # Print as a table with clean formatting
            self.logger.info(
                "\n"
                + str(
                    tabulate(
                        table_data,
                        headers=all_columns,
                        tablefmt="grid",
                        stralign="left",
                        maxcolwidths=[25, 25, 40, 20],
                    )
                )
            )
        else:
            self.logger.info("No diagnostic data to display.")

    def diagnostic_summary(self) -> None:
        """
        Prints a summary of diagnostic codes and their occurrences.
        Returns:
            None
        """
        if not self.diagnostics:
            self.logger.info("No diagnostics to summarize.")
            return

        code_count = defaultdict(int)
        for diag in self.diagnostics:
            for code in diag.get("codes", []):
                code_count[code] += 1

        self.logger.info("\n📊 Diagnostic Codes Summary:")
        table = [[code, count] for code, count in code_count.items()]
        self.logger.info(
            "\n"
            + tabulate(
                table, headers=["Diagnostic Code", "Occurrences"], tablefmt="grid"
            )
        )

    def filter_unique_diagnostics(self, diagnostic_data: List[dict]) -> dict:
        """
        Filters and merges diagnostic entries to ensure uniqueness based on diagnostic codes.
        Args:
            diagnostic_data (list): A list of diagnostic entries to be filtered.
        Returns:
            dict: A dictionary with unique diagnostic codes as keys and lists of associated entries as values.
        """
        merged_codes = defaultdict(list)
        unique_tracker = defaultdict(set)

        for item in diagnostic_data:
            codes = item.get("codes", {})
            for code, entries in codes.items():
                for entry in entries:
                    if isinstance(entry, str) and entry.strip() == code:
                        continue
                    if isinstance(entry, dict):
                        mew_entry = {k: v for k, v in entry.items() if v != code}
                        entry_tuple = tuple(sorted(mew_entry.items()))
                    elif isinstance(entry, (list, tuple)):
                        entry_tuple = tuple(entry)
                    else:
                        entry_tuple = (entry,)
                    if entry_tuple not in unique_tracker[code]:
                        unique_tracker[code].add(entry_tuple)
                        entry_data = (
                            {k: v for k, v in entry.items() if v != code}
                            if isinstance(entry, dict)
                            else entry
                        )
                        if entry_data:
                            merged_codes[code].append(entry_data)
        merged_codes = dict(merged_codes)
        return merged_codes
