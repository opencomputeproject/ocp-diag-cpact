"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

===========================================================================
DiagnosticAnalysis is a rule-based analysis class used to extract diagnostic codes and context
from textual output. It applies regex-based rules to identify patterns, update diagnostic context,
and track matched codes for reporting and validation.

Features:
- Applies diagnostic rules using named or unnamed regex groups.
- Supports flexible rule formats including search_string and diagnostic_search_string.
- Updates diagnostic context and result collector with matched parameters and codes.
- Handles duplicate matches and ensures uniqueness in diagnostic mapping.
- Logs rule application, match status, and diagnostic updates.

Classes:
    DiagnosticAnalysis:
        Extends BaseAnalysis to perform diagnostic evaluation on output logs.

Usage:
    Instantiate DiagnosticAnalysis with a list of rules and optional step ID.
    Call `analyze(output, context)` to apply rules and update diagnostics.
    Each rule may define:
        - search_string or diagnostic_search_string (regex pattern)
        - diagnostic_result_code (named group or static value)
        - parameter_to_set (context key to update)
==============================================================================
"""

import json
import re
from collections import defaultdict, OrderedDict
from analysis.base_analysis import BaseAnalysis
from result_builder.result_builder import ResultCollector
from core.context import Context
from typing import Any, Type


class DiagnosticAnalysis(BaseAnalysis):
    def __init__(self, rules: list[dict], step_id: str | None) -> None:
        """
        Initialize the DiagnosticAnalysis with given rules and optional step ID.
        Args:
            rules (list): A list of diagnostic analysis rules or criteria.
            step_id (str, optional): An identifier for the step being analyzed. Defaults to None.
        Returns:
            None
        """
        super().__init__(rules, step_id=step_id)
        self.rules = rules

    def analyze(self, output: Any, context: Type[Context]) -> dict:
        """
        Analyze the given output based on the initialized rules and context.
        Args:
            output (str): The output string to be analyzed.
            context: The context object to update with diagnostic information.
        Returns:
            list: A list of diagnostic findings or results.
        """
        diagnostics_map = defaultdict(list)
        for rule in self.rules:
            self.logger.info("---------------- Applying Rule ----------------")
            search_string = rule.get("search_string")
            diagnostic_result_code = rule.get("diagnostic_result_code")
            diagnostic_search_string = rule.get("diagnostic_search_string")
            if search_string and diagnostic_search_string:
                self.logger.warning(
                    "Both search_string and diagnostic_search_string are provided in rule. Using diagnostic_search_string for analysis."
                )
                continue
            if search_string and not diagnostic_result_code:
                self.logger.warning(
                    "search_string provided without diagnostic_result_code. Skipping this rule."
                )
                continue
            if diagnostic_search_string and diagnostic_result_code:
                self.logger.warning(
                    "diagnostic_search_string provided with diagnostic_result_code. Using diagnostic_search_string for analysis."
                )
                continue
            pattern = search_string or diagnostic_search_string
            parameter_to_set = rule.get("parameter_to_set")
            diagnostic_result_codes = self.search_and_manage(
                regex_key=pattern,
                log_data=output,
                entry=rule,
                diagnostics_map=diagnostics_map,
            )
            if parameter_to_set:
                self.logger.info(
                    f"🔍 Matched '{pattern}' → {True if  diagnostic_result_codes else False} → set {parameter_to_set}"
                )
                context.update_diagnostic_context(
                    tc_id=context.get("test_id"),
                    step_id=self.step_id,
                    key=parameter_to_set,
                    value=True if diagnostic_result_codes else False,
                )
                ResultCollector.get_instance().add_diagnostic_keys(
                    tc_id=context.get("test_id"),
                    step_id=self.step_id,
                    key=parameter_to_set,
                    value=True if diagnostic_result_codes else False,
                )
            if search_string and diagnostic_result_codes:
                self.logger.info(
                    f"🔍 Updated diagnostic context: {context.get_diagnostic_context()}"
                )
                # for code in diagnostic_result_codes:
                context.add_diagnostic_code(
                    tc_id=context.get("test_id"),
                    step_id=self.step_id,
                    codes=diagnostic_result_codes,
                )
            if diagnostic_search_string and diagnostic_result_codes:
                self.logger.info(
                    f"🔍 Updated diagnostic context: {context.get_diagnostic_context()}"
                )
                # for code in diagnostic_result_codes:
                context.add_diagnostic_code(
                    tc_id=context.get("test_id"),
                    step_id=self.step_id,
                    codes=diagnostic_result_codes,
                )
            ResultCollector.get_instance().add_diagnostic(
                scenario_id=context.get("test_id"),
                step_id=self.step_id,
                codes=diagnostic_result_codes,
                message="Found codes: ",
            )
        self.logger.info("---------------- Diagnostic Keys ----------------")
        return diagnostics_map
    
    def search_and_manage(
        self, regex_key: str, log_data: str, entry: dict, diagnostics_map: dict
    ) -> dict:
        """
        Search the log data using the provided regex pattern and manage the diagnostics map.
        Args:
            regex_key (str): The regex pattern to search for.
            log_data (str): The log data to be searched.
            entry (dict): The diagnostic rule entry containing additional information.
            diagnostics_map (dict): The map to store diagnostic results.
        Returns:
            dict: Updated diagnostics map with found results.
        """
        pattern = re.compile(regex_key, re.DOTALL | re.MULTILINE)
        matches = pattern.finditer(log_data)
        for match in matches:
            diagnostic_result_code = None
            matched_groups = match.groupdict()
            all_groups = match.groups()
            # CASE 1: diagnostic_result_code refers to a named regex group
            if (
                "diagnostic_result_code" in entry
                and entry["diagnostic_result_code"] in matched_groups
            ):
                diagnostic_result_code = matched_groups[entry["diagnostic_result_code"]]

            # CASE 2: diagnostic_result_code is a fixed value
            elif "diagnostic_result_code" in entry:
                diagnostic_result_code = entry["diagnostic_result_code"]

            # CASE 3: no explicit code, try to infer from first group
            elif matched_groups:
                diagnostic_result_code = str(next(iter(matched_groups.values()), None))
            elif all_groups:
                diag_tuple = tuple(group for group in all_groups if group)
                if len(diag_tuple) >= 2:
                    diagnostic_result_code = str(diag_tuple)
                else:
                    diagnostic_result_code = str(all_groups[0])

            if not diagnostic_result_code:
                continue

            # Include all named or unnamed groups dynamically
            group_data = {}
            if matched_groups:
                group_data = matched_groups
            else:
                d = []
                if len(all_groups) == 1:
                    group_data = all_groups[0]
                    d.append(all_groups[0])
                else:
                    for idx, group in enumerate(all_groups):
                        if group:
                            d.append(group)
                if d:
                    group_data = d
            if diagnostic_result_code not in diagnostics_map:
                diagnostics_map[diagnostic_result_code] = []
            if group_data and group_data not in diagnostics_map[diagnostic_result_code]:
                diagnostics_map[diagnostic_result_code].append(group_data)
        return dict(diagnostics_map)
