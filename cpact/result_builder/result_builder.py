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
import os
import re
from collections import defaultdict
import copy
import json
import threading
from time import time
from zipfile import Path
from tabulate import tabulate
import pprint
import pandas as pd
import textwrap
from collections.abc import Mapping, Sequence
from typing import Any, Dict, List, Optional, Union
from typing import Any, Dict, FrozenSet, Iterable, Mapping, Optional, List, Sequence, Tuple, Type
from copy import deepcopy
from cpact.utils.logger_utils import TestLogger
from cpact.utils.custom_exception_handler import CustomExceptionHandler



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
        self.scenario_output = {}

    def add_step_result(
        self,
        scenario_name: str,
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
        self.add_scenario_output(scenario_name=scenario_name,
                                 step_output=result)
        self.logger.debug(f"==================== Step Result {step_name} ====================")
        self.logger.debug(
            f"\n"
            f"{'Scenario ID:':<20}{scenario_id}\n"
            f"{'Step ID:':<20}{step_id}\n"
            f"{'Step Name:':<20}{step_name}\n"
            f"{'Step Type:':<20}{step_type}\n"
            f"{'Status:':<20}{status}\n"
            f"{'Duration:':<20}{duration:.3f} seconds\n"
            f"{'Message:':<20}{message}"
        )
        self.logger.debug("=====================================================")

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
        self, scenario_id: str, step_id: str, codes: list[str], message: str = "",
        parent_scenario: str = ""
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
        existing = next(
            (
                d for d in self.diagnostics
                if d["parent_scenario"] == parent_scenario
                and d["scenario_id"] == scenario_id
                and d["step_id"] == step_id
            ),
            None,
        )

        if existing:
            # Merge codes into existing entry
            for code_key, code_value in codes.items():
                if code_key in existing["codes"]:
                    if isinstance(existing["codes"][code_key], list) and isinstance(code_value, list):
                        existing["codes"][code_key].extend(code_value)
                    else:
                        existing["codes"][code_key] = {"Message": code_value}
                else:
                    existing["codes"][code_key] = {"Message": code_value}
        else:
            # Add as new diagnostic
            self.diagnostics.append(
                {
                    "parent_scenario": parent_scenario,
                    "scenario_id": scenario_id,
                    "step_id": step_id,
                    "codes": codes,
                    "message": message,
                }
            )
        self.diagnostics_codes.extend(codes)

    def _extend_or_set(self, target: Dict[str, Any], key: str, value: Any, dedupe: bool = False) -> None:
        """
        Merge value into target[key].
        - If both existing and new values are lists -> extend (optionally dedupe).
        - Otherwise -> replace.
        """
        if key in target and isinstance(target[key], list) and isinstance(value, list):
            if dedupe:
                # extend while avoiding duplicates (preserves original order)
                seen = set(target[key])
                for item in value:
                    tup = item if not isinstance(item, dict) else tuple(sorted(item.items()))
                    if tup not in seen:
                        target[key].append(item)
                        seen.add(tup)
            else:
                target[key].extend(value)
        else:
            target[key] = deepcopy(value)


    def add_scenario_output(
        self,
        scenario_name: str,
        step_output: Optional[Dict[str, Any]] = None,
        scenario_output: Optional[Dict[str, Any]] = None,
        diag_codes: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, Any]] = None,
        *,
        dedupe_diag_entries: bool = False
    ) -> None:
        """
        Add or merge outputs for a scenario.

        Behaviour:
        - Creates a new scenario entry if not present.
        - Merges scenario_output into headers (only updates/sets keys).
        - Appends step_output into headers['step_details'].
        - Merges diag_codes into diagnostic_result_codes:
            * if a code key exists and both are lists -> extend (optionally dedupe)
            * otherwise replace.

        Parameters:
        - scenario_name: name/key for scenario_output dict
        - step_output: single step dict to append to step_details
        - scenario_output: dict to update headers (e.g. status/start_time/end_time)
        - diag_codes: dict of diagnostic codes (e.g. {"Error_Code": [...]})
        - dedupe_diag_entries: if True, avoid adding duplicate items when merging lists
        """
        # Ensure container exists
        if scenario_name not in self.scenario_output:
            self.scenario_output[scenario_name] = {
                "headers": {},
                "results": {
                    "step_details": []
                },
                "diagnostic_result_codes": {}
            }

        entry = self.scenario_output[scenario_name]

        # Merge scenario_output into results (only top-level keys)
        if scenario_output:
            # Only allow certain header keys to be updated; preserves structure
            allowed_header_keys = {"status", "start_time", "end_time"}
            for k, v in scenario_output.items():
                if k in allowed_header_keys:
                    entry["results"][k] = deepcopy(v)
                else:
                    # for unexpected header keys, either ignore or set them explicitly
                    # choose to set them so we remain flexible
                    entry["results"][k] = deepcopy(v)
        if headers:
            for k, v in headers.items():
                entry["headers"][k] = deepcopy(v)
        # Append step_output into step_details
        if step_output:
            entry["results"].setdefault("step_details", [])
            # avoid modifying the caller's dict
            entry["results"]["step_details"].append(deepcopy(step_output))

        # Merge diagnostic codes
        if diag_codes:
            entry.setdefault("diagnostic_result_codes", {})
            for code_key, code_value in diag_codes.items():
                self._extend_or_set(
                    entry["diagnostic_result_codes"],
                    code_key,
                    deepcopy(code_value),
                    dedupe=dedupe_diag_entries
                )


    def dump_scenario_output(self, file_path:str) -> None:
        import json
        with open(file_path, "w") as f:
            json.dump(self.scenario_output, f, indent=4)
        self.logger.info(f"Results saved to {file_path}")

    def dump_custom_scenario_output(self, file_path:str, scenario_output: str) -> None:
        import json
        with open(file_path, "w") as f:
            json.dump(scenario_output, f, indent=4)
        # self.logger.info(f"Results for scenario '{scenario_output}' saved to {file_path}")
    
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

    def dump_diagnostics(self, file_path: str, dump_data: dict) -> None:
        """
        Save only the diagnostics to a JSON file.
        Args:
            file_path (str): The path to the file where diagnostics should be saved.
        Returns:
            None
        """
        import json
        import re
        if not dump_data:
            data = self.filter_unique_diagnostics(self.diagnostics)
            with open(file_path, "w") as f:
                json.dump(data, f, indent=4)
        else:
            data = self.build_drc_summary(dump_data)
            with open(file_path, "w") as f:
                json.dump(data, f, indent=4)
        self.logger.info(f"Diagnostics saved to {file_path}")


    def find_first_key(self, data: Any, target_key: str) -> Optional[Any]:
        """
        Recursively search nested dict/list and return the first value for target_key.

        Args:
            data: Input nested structure (dict/list/other).
            target_key: Key name to locate.

        Returns:
            Value associated with target_key if found, else None.
        """
        if isinstance(data, Mapping):
            if target_key in data:
                return data[target_key]
            for value in data.values():
                found = self.find_first_key(value, target_key)
                if found is not None:
                    return found

        elif isinstance(data, Sequence) and not isinstance(data, (str, bytes, bytearray)):
            for item in data:
                found = self.find_first_key(item, target_key)
                if found is not None:
                    return found

        return None


    def build_drc_summary(self, report: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
        """
        Create a new dictionary by browsing `diagnostic_result_codes` and aggregating
        its entries per DRC key.

        This function:
        - Locates `diagnostic_result_codes` inside the input report.
        - Iterates each DRC code.
        - Appends all entry dicts under that DRC into `entries`.
        - Computes `total_count` as the number of entries (or from DRC_count if valid).

        Args:
            report: Full report dict (like the JSON you shared) OR any dict containing
                    `diagnostic_result_codes` somewhere inside.

        Returns:
            New aggregated dictionary keyed by DRC code.
            Example:
                {
                "FAIL-...": {"total_count": 3, "entries": [..]},
                ...
                }
        """
        drc_block = self.find_first_key(report, "diagnostic_result_codes")
        if not isinstance(drc_block, Mapping):
            return {}

        new_dict: Dict[str, Dict[str, Any]] = {}

        for drc_code, items in drc_block.items():
            if not isinstance(items, list):
                # Normalize non-list payloads into a list so appending is consistent.
                items = [items]

            bucket = new_dict.setdefault(drc_code, [])
            for entry in items:
                if not isinstance(entry, Mapping):
                    # Skip unexpected entry types safely.
                    continue

                bucket.append(dict(entry))

                # Prefer numeric DRC_count if present, else count each entry as 1.
                # drc_count = entry.get("DRC_count")
                # if isinstance(drc_count, int):
                #     bucket["total_count"] += drc_count
                # elif isinstance(drc_count, str) and drc_count.isdigit():
                #     bucket["total_count"] += int(drc_count)
                # else:
                #     bucket["total_count"] += 1

        return new_dict

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
                            else {"message": entry}
                        )
                        if entry_data:
                            merged_codes[code].append(entry_data)
        merged_codes = dict(merged_codes)
        return merged_codes

    def _make_signature(self, entry: Dict[str, Any]) -> FrozenSet[Tuple[str, str]]:
        """
        Build an order-independent signature from entry by including all key/value pairs
        except ignored keys and keys with empty-string values. Values are JSON-dumped
        to handle nested types deterministically.
        """
        items = []
        _IGNORED_KEYS = {"message", "component", "confidence", "actions", "DRC_count"}
        for k, v in entry.items():
            if k in _IGNORED_KEYS:
                continue
            # skip empty-string values
            if isinstance(v, str) and v.strip() == "":
                continue
            # convert to stable string representation
            try:
                sval = json.dumps(v, sort_keys=True, ensure_ascii=False)
            except Exception as e:
                CustomExceptionHandler.print_exception(e)
                sval = str(v)
            items.append((k, sval))
        return frozenset(items)

    def _safe_int(self, val: Any) -> int | None:
        """Return int if convertible, else None."""
        if val is None:
            return None
        if isinstance(val, int):
            return val
        if isinstance(val, str) and val.strip() != "":
            try:
                return int(val)
            except ValueError:
                try:
                    return int(float(val))
                except Exception:
                    return None
        return None

    def filter_historical_data(self, historical_data_files: Iterable[str], current_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update current_data in memory by scanning historical_data_files and incrementing DRC_count.

        Arguments:
        - historical_data_files: iterable of file paths (JSON files).
        - current_data: dict in the same structure you already use (top-level keys mapping to objects
                        which contain 'diagnostic_result_codes' maps like in your sample).

        Returns:
        - updated current_data (the same dict object, modified in place).
        """

        # Build index: top_key -> diag_code -> signature -> count
        hist_index: Dict[str, Dict[str, Dict[FrozenSet[Tuple[str, str]], int]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
        self.logger.info("Building historical data index...")
        for hist_path in historical_data_files:
            try:
                with open(hist_path, "r", encoding="utf-8") as fh:
                    hist_obj = json.load(fh)
            except Exception:
                self.logger.warning(f"Failed to read/parse historical data file: {hist_path}")
                # skip unreadable/malformed files (optional: log)
                continue
            # We expect structure like your sample: top-level keys -> dicts that contain "diagnostic_result_codes"
            # Fallbacks: if the file itself is directly diagnostic_result_codes map, handle that too.
            self.logger.info(f"Processing historical data file: {hist_path}")
            candidates = []
            if isinstance(hist_obj, dict) and "diagnostic_result_codes" in hist_obj and isinstance(hist_obj["diagnostic_result_codes"], dict):
                # e.g. { "<name>": { "diagnostic_result_codes": {...} }, ... } not likely here but handle cleanly
                # If the file is a single block with diagnostic_result_codes at top, treat that as unnamed.
                # We'll assign it under an empty key so it doesn't match named current_data keys (only named ones will match).
                candidates.append(("", hist_obj["diagnostic_result_codes"]))
            elif isinstance(hist_obj, dict):
                # find nested blocks that have diagnostic_result_codes
                for top_key, top_val in hist_obj.items():
                    if isinstance(top_val, dict) and "diagnostic_result_codes" in top_val and isinstance(top_val["diagnostic_result_codes"], dict):
                        candidates.append((top_key, top_val["diagnostic_result_codes"]))
                # fallback: maybe the file itself maps diag_code -> [..]
                if not candidates:
                    maybe = {k: v for k, v in hist_obj.items() if isinstance(v, list)}
                    if maybe:
                        # use top-level filename-like key to avoid accidental cross-match; we won't normally find this key in current_data
                        candidates.append(("", maybe))

            for top_key, diag_map in candidates:
                for diag_code, entries in diag_map.items():
                    if not isinstance(entries, list):
                        continue
                    for entry in entries:
                        if not isinstance(entry, dict):
                            continue
                        sig = self._make_signature(entry)
                        hist_index[top_key][diag_code][sig] += 1
        # with open("hist_index_debug.json", "w", encoding="utf-8") as debug_fh:
            # json.dump({k: {dk: {str(sk): v for sk, v in dct.items()} for dk, dct in dm.items()} for k, dm in hist_index.items()}, debug_fh, indent=4)
        # Now process current_data and apply increments using hist_index
        for top_key, current_block in current_data.items():
            # try to find diagnostic_result_codes inside current_block (similar to your original code)
            diag_map = {}
            if isinstance(current_block, dict) and "diagnostic_result_codes" in current_block and isinstance(current_block["diagnostic_result_codes"], dict):
                diag_map = current_block["diagnostic_result_codes"]
                hist_sub_index = hist_index.get(top_key, {})  # use same top_key to match historical blocks
            elif isinstance(current_block, dict):
                # maybe current_block itself is diag_map (fallback)
                maybe = {k: v for k, v in current_block.items() if isinstance(v, list)}
                if maybe:
                    diag_map = maybe
                    hist_sub_index = hist_index.get("", {})  # fallback to unnamed block index
                else:
                    # nothing to do for this top_key
                    self.logger.debug(f"No diagnostic_result_codes found for top-level key '{top_key}', skipping.")
                    continue
            else:
                self.logger.debug(f"Top-level key '{top_key}' is not a dict, skipping.")
                continue

            for diag_code, curr_entries in diag_map.items():
                if not isinstance(curr_entries, list):
                    continue
                # get hist mapping for this diag_code (may be empty dict)
                hist_code_map = hist_sub_index.get(diag_code, {})
                for entry in curr_entries:
                    if not isinstance(entry, dict):
                        continue
                    sig = self._make_signature(entry)
                    hist_count = hist_code_map.get(sig, 0)
                    existing = self._safe_int(entry.get("DRC_count"))

                    if existing is not None:
                        # increment existing by number of historical matches
                        entry["DRC_count"] = str(existing + hist_count)
                    else:
                        # no existing count: if we found matches in history, set hist_count + 1 (count current occurrence)
                        # otherwise set 1
                        if hist_count > 0:
                            entry["DRC_count"] = str(hist_count + 1)
                        else:
                            entry["DRC_count"] = "1"

        return current_data

    def get_action_for_drc(self, actions_obj: Any, drc_value: int) -> Tuple[Optional[int], Optional[Any]]:
        """
        Accepts either:
        - actions_obj as a list of dicts: [{"1":"..."}, {"5":"..."}]
        - or actions_obj as a dict: {"1": "...", "5": "..."}
        Returns (selected_key:int, selected_value) or (None, None) if no actions available.

        Selection rules:
        1) exact match for drc_value
        2) else largest key <= drc_value
        3) else smallest available key
        Keys can be strings or ints; values preserved as-is.
        """
        if not actions_obj:
            self.logger.debug("No actions object provided, returning (None, None)")
            return None, None

        # Build a normalized map: int -> value
        action_map: Dict[int, Any] = {}
        try:
            if isinstance(actions_obj, dict):
                for k, v in actions_obj.items():
                    try:
                        action_map[int(k)] = v
                    except Exception:
                        # ignore non-numeric keys
                        self.logger.debug(f"Ignoring non-numeric action key: {k}")
                        continue
            elif isinstance(actions_obj, list):
                for item in actions_obj:
                    if not isinstance(item, dict):
                        continue
                    # each item expected to have a single key
                    for k, v in item.items():
                        try:
                            action_map[int(k)] = v
                        except Exception:
                            continue
            else:
                self.logger.debug(f"Unknown actions_obj type: {type(actions_obj)}, returning (None, None)")
                # unknown type
                return None, None
        except Exception as e:
            CustomExceptionHandler.print_exception(e)
            self.logger.debug("Exception occurred while processing actions_obj, returning (None, None)")
            return None, None

        if not action_map:
            self.logger.debug("No valid actions found in actions_obj, returning (None, None)")
            return None, None

        available_keys = sorted(action_map.keys())

        # 1. exact match
        if drc_value in action_map:
            self.logger.debug(f"Exact match found for DRC value {drc_value}")
            return drc_value, deepcopy(action_map[drc_value])

        # 2. largest <= drc_value
        less_or_equal = [k for k in available_keys if k <= drc_value]
        if less_or_equal:
            best_key = max(less_or_equal)
            return best_key, deepcopy(action_map[best_key])

        # 3. fallback: smallest key
        smallest = available_keys[0]
        self.logger.debug(f"Fallback to smallest action key {smallest} for DRC value {drc_value}")
        return smallest, deepcopy(action_map[smallest])

    def filter_map_file(self, current_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        For each top-level block in current_data, read the map_file (headers.map_file)
        and merge matching map entries into each diagnostic entry (in-place).
        Returns the same current_data dict (mutated).
        """
        # cache map file JSON by resolved path
        map_cache: Dict[str, Optional[Dict[str, Any]]] = {}

        def _load_map_file(scenario_path: str, map_file_path: str) -> Optional[Dict[str, Any]]:
            if not map_file_path:
                return None
            try:
                scenario_path = os.path.dirname(scenario_path)
                scenario_dir = os.path.abspath(scenario_path)
                if os.path.dirname(map_file_path):
                    resolved_map_file = map_file_path
                else:
                    resolved_map_file = os.path.join(scenario_dir, map_file_path)
                # p = resolved_map_file#str(Path(resolved_map_file).resolve())
            except Exception:
                p = map_file_path
            if resolved_map_file in map_cache:
                return map_cache[resolved_map_file]
            try:
                with open(resolved_map_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                    map_cache[resolved_map_file] = data if isinstance(data, dict) else {}
            except Exception:
                map_cache[resolved_map_file] = None
            return map_cache[resolved_map_file]

        def _get_drc_count(entry: Dict[str, Any]) -> int:
            if hasattr(self, "_safe_int") and callable(getattr(self, "_safe_int")):
                val = self._safe_int(entry.get("DRC_count"))
                return val if val is not None else 1
            # fallback: try parse int, default to 1
            raw = entry.get("DRC_count")
            try:
                if raw is None or str(raw).strip() == "":
                    return 1
                return int(raw)
            except Exception:
                try:
                    return int(float(raw))
                except Exception:
                    return 1
        def get_map_entry_for_code(map_data: Dict[str, Any], code_key: str) -> Optional[Union[Dict[str, Any], List[Any]]]:
            """
            Search map_data for a matching entry:
            1. First, try exact match for code_key.
            2. If not found, try regex matching against map keys.
            3. Return the matched entry or None.
            """
            
            # 1. Try exact match first
            if code_key in map_data:
                return map_data[code_key]
            
            # 2. Try regex matching
            for map_key, map_value in map_data.items():
                try:
                    # Treat map_key as a regex pattern
                    if re.match(map_key, code_key):
                        self.logger.debug(f"Regex match found: '{map_key}' matched code_key '{code_key}'")
                        return map_value
                except re.error:
                    # If map_key is not a valid regex, skip it
                    self.logger.debug(f"Invalid regex pattern in map: '{map_key}'")
                    continue
            
            # 3. No match found
            self.logger.debug(f"No exact or regex match found for code_key '{code_key}' in map_data")
            return None
        
        def _remove_code_key_from_entry(entry: Dict[str, Any], code_key: str) -> None:
            """
            Remove code_key if it appears as:
            1) a key in entry
            2) a value in entry (value == code_key)
            Mutates entry in-place.
            """
            keys_to_remove = []

            for k, v in entry.items():
                if k == code_key:
                    keys_to_remove.append(k)
                elif isinstance(v, str) and v == code_key:
                    keys_to_remove.append(k)

            for k in keys_to_remove:
                entry.pop(k, None)
        # iterate top-level blocks
        for top_key, current_block in list(current_data.items()):
            if not isinstance(current_block, dict):
                continue

            headers = current_block.get("headers", {}) or {}
            diag_codes = current_block.get("diagnostic_result_codes", {}) or {}

            map_file_path = headers.get("map_file", "")
            scenario_path = headers.get("scenario_path", "")
            map_data = _load_map_file(scenario_path, map_file_path)
            if not map_data:
                # no valid map file for this block
                self.logger.warning(f"Skipping map merge for '{top_key}': no valid map file at '{map_file_path}'")
                continue
            self.logger.info(f"Merging map data from '{map_file_path}' into diagnostics for '{top_key}'")
            # iterate diag codes
            for code_key, code_entries in diag_codes.items():
                if not isinstance(code_entries, list):
                    self.logger.warning(f"Skipping code '{code_key}' in '{top_key}': entries not a list")
                    continue
                map_entry_for_code = get_map_entry_for_code(map_data, code_key)
                # map_entry_for_code = map_data.get(code_key)
                if not map_entry_for_code:
                    for ent in code_entries:
                        ent.setdefault("message", "Map data is unavailable")
                        ent.setdefault("component", "Map data is unavailable")
                        ent.setdefault("confidence", "Map data is unavailable")
                        ent.setdefault("actions", "Map data is unavailable")
                    self.logger.debug(f"No map entry for code '{code_key}' in '{top_key}'")
                    continue
                # normalize map entries into a list of dicts (so below logic is uniform)
                if isinstance(map_entry_for_code, dict):
                    map_entries_list = [map_entry_for_code]
                elif isinstance(map_entry_for_code, list):
                    map_entries_list = [m for m in map_entry_for_code if isinstance(m, dict)]
                    if not map_entries_list:
                        continue
                else:
                    continue

                # process each diagnostic entry in-place
                for entry in code_entries:
                    if not isinstance(entry, dict):
                        continue

                    drc_count = _get_drc_count(entry)

                    matched_map_base: Optional[Dict[str, Any]] = None
                    matched_action_key: Optional[int] = None
                    matched_action_value: Optional[Any] = None

                    # Search map entries for a match (stop at first matched map base that has actions)
                    for map_base in map_entries_list:
                        actions = map_base.get("actions")
                        key, val = self.get_action_for_drc(actions, drc_count)
                        if key is not None:
                            matched_map_base = map_base
                            matched_action_key = key
                            matched_action_value = val
                            self.logger.debug(f"Matched map entry for code '{code_key}' with DRC_count={drc_count} using action key={key}")
                            break
                        # if map_base has no actions but has other fields, we may still use the map_base later
                        # (so don't continue searching forever). We'll prefer map_base with actions when present.

                    # Merge logic:
                    # 1) start with base map fields (excluding "actions")
                    # 2) overlay matched_action under 'actions' (as {str(key): value})
                    # 3) finally overlay existing entry fields so entry's own fields take precedence
                    merged_fields: Dict[str, Any] = {}

                    if matched_map_base:
                        for k, v in matched_map_base.items():
                            if k == "actions":
                                continue
                            merged_fields[k] = deepcopy(v)
                    # insert matched action under "actions" key (only if we found it)
                    if matched_action_key is not None:
                        # represent actions the same way map uses: list of single-key dict, but to keep simple we store single dict
                        # as {"<key>": <value>} so it's clear. Adjust structure if you prefer a list.
                        merged_fields.setdefault("actions", {})
                        merged_fields["actions"] = deepcopy(matched_action_value)

                    # finally overlay entry itself so it wins
                    # entry fields override any map fields
                    for k, v in entry.items():
                        merged_fields[k] = deepcopy(v)

                    # Replace entry content in-place (entry object is updated, insertion order preserved)
                    entry.clear()

                    entry.update(merged_fields)
                    _remove_code_key_from_entry(entry, code_key)
                    self.logger.debug(f"Updated entry for code '{code_key}' in '{top_key}' with merged fields")
        return current_data