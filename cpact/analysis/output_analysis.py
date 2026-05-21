"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

================================================================================
OutputAnalysis is a rule-based analysis class used to evaluate textual output from test steps
against predefined regex patterns. It updates diagnostic context and result tracking based on
matches found in the output.

Features:
- Applies multiple regex-based rules to step output.
- Updates diagnostic context keys for each match.
- Integrates with Context and ResultCollector for centralized tracking.
- Logs rule application, match status, and diagnostic updates.
- Returns structured results for downstream processing.

Classes:
    OutputAnalysis:
        Extends BaseAnalysis to perform regex-based output evaluation.

Usage:
    Instantiate OutputAnalysis with a list of rules and optional step ID.
    Call `analyze(output, context)` to apply rules and update diagnostics.
    Each rule should define a `regex` pattern and a `parameter_to_set` key.
==============================================================================
"""

import re
from typing import Any, Type, List

from cpact.core.context import Context
from cpact.analysis.base_analysis import BaseAnalysis
from cpact.result_builder.result_builder import ResultCollector


class OutputAnalysis(BaseAnalysis):
    def __init__(self, rules: list, step_id: str = None) -> None:
        """
        Initializes the rule-based processor with a list of rules and an optional step identifier.

        Args:
            rules (list): A list of rule definitions to be applied.
            step_id (str): Optional identifier for the step being processed.

        Returns:
            None
        """
        super().__init__(rules, step_id=step_id)
        self.rules = rules

    def analyze(self, output: Any, context: Type[Context], validator_type: str) -> List[dict]:
        """
        Analyzes the given output string against the defined rules and updates the context with diagnostic information
        based on the matches found.
        Args:
            output (str): The output string to be analyzed.
            context: The context object to be updated with diagnostic information.
            validator_type (str): The type of validator to use for analysis.
        Returns:
            list: A list of dictionaries containing the results of the analysis.
        """
        diagnostic_code = {}
        results = []
        self.logger.info(f"🔍 Analyzing output with {len(self.rules)} rules")
        for rule in self.rules:
            self.logger.info("---------------- Applying Rule ----------------")
            self.logger.info(f"🔍 Applying rule: {rule}")
            pattern = rule["regex"]
            key = rule["parameter_to_set"]
            match = re.search(pattern, output)
            value = bool(match)
            self.logger.info(f"🔍 Matched '{pattern}' → {value} → set {key}")
            context.update_diagnostic_context(
                tc_id=context.get("test_id"), step_id=self.step_id, key=key, value=value
            )
            self.logger.debug(
                f"🔍 Updated diagnostic context: {context.get_diagnostic_context()}"
            )
            ResultCollector.get_instance().add_diagnostic_keys(
                tc_id=context.get("test_id"), step_id=self.step_id, key=key, value=value
            )

            self.logger.debug(f"🔍 Added diagnostic key: {key} = {value}")
            self.logger.info(
                f"🔍 Diagnostic codes: {ResultCollector.get_instance().get_diagnostic_keys(context.get('test_id'))}"
            )
            self.logger.info("---------------- Diagnostic Keys ----------------")
            results.append({key: value})
        return results
