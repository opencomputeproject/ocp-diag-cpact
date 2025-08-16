
"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.
"""

import re

from analysis.base_analysis import BaseAnalysis
from result_builder.result_builder import ResultCollector

class OutputAnalysis(BaseAnalysis):
    def __init__(self, rules: list):
        super().__init__(rules)
        self.rules = rules

    def analyze(self, output: str, context) -> list:
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
            context.update_diagnostic_context(context.get("test_id"), key, value)
            self.logger.debug(f"🔍 Updated diagnostic context: {context.get_diagnostic_context()}")
            ResultCollector.get_instance().add_diagnostic_keys(context.get("test_id"), key, value)
            
            self.logger.debug(f"🔍 Added diagnostic key: {key} = {value}")
            self.logger.info(f"🔍 Diagnostic codes: {ResultCollector.get_instance().get_diagnostic_keys(context.get('test_id'))}")
            self.logger.info("---------------- Diagnostic Keys ----------------")
            results.append({key: value})
        return results
