"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.
"""

import re

from analysis.base_analysis import BaseAnalysis
from result_builder.result_builder import ResultCollector

class DiagnosticAnalysis(BaseAnalysis):
    def __init__(self, rules: list):
        super().__init__(rules)
        self.rules = rules

    def analyze(self, output: str, context) -> list:
        findings = []
        for rule in self.rules:
            self.logger.info("---------------- Applying Rule ----------------")
            search_string = rule.get("search_string")
            diagnostic_result_code = rule.get("diagnostic_result_code")
            diagnostic_search_string = rule.get("diagnostic_search_string")
            if search_string and diagnostic_search_string:
                self.logger.warning("Both search_string and diagnostic_search_string are provided in rule. Using diagnostic_search_string for analysis.")
                continue
            if search_string and not diagnostic_result_code:
                self.logger.warning("search_string provided without diagnostic_result_code. Skipping this rule.")
                continue
            if diagnostic_search_string and diagnostic_result_code:
                self.logger.warning("diagnostic_search_string provided with diagnostic_result_code. Using diagnostic_search_string for analysis.")
                continue
            pattern = search_string or diagnostic_search_string
            parameter_to_set = rule.get("parameter_to_set")
            # code = rule.get("fault_code")
            # msg = rule.get("message")
            match = re.search(pattern, output)
            
            value = bool(match)
            if parameter_to_set:
                self.logger.info(f"🔍 Matched '{pattern}' → {value} → set {parameter_to_set}")
                context.update_diagnostic_context(context.get("test_id"), parameter_to_set, value)
                ResultCollector.get_instance().add_diagnostic_keys(context.get("test_id"), parameter_to_set, value)
            if search_string and match:
                self.logger.info(f"🔍 Updated diagnostic context: {context.get_diagnostic_context()}")
                context.add_diagnostic_code(context.get("test_id"), diagnostic_result_code, match.group() if match else "")
                ResultCollector.get_instance().add_diagnostic(scenario_id=context.get("test_id"), 
                                                              code=diagnostic_result_code, match_text=match.group() if match else "")
            if diagnostic_search_string and match:
                self.logger.info(f"🔍 Updated diagnostic context: {context.get_diagnostic_context()}")
                diagnostic_result_code =  match.group() if match else ""
                context.add_diagnostic_code(context.get("test_id"), diagnostic_result_code, diagnostic_result_code)
                ResultCollector.get_instance().add_diagnostic(scenario_id=context.get("test_id"),
                                                              code=diagnostic_result_code, match_text=match.group() if match else "")
            self.logger.info("---------------- Diagnostic Keys ----------------")
            
            if match:
                finding = {
                    "fault_code": diagnostic_result_code,
                    "match": match.group()
                }
                findings.append(finding)
        return findings
