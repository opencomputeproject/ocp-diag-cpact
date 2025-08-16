"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.
"""

from analysis.output_analysis import OutputAnalysis
from analysis.diagnostic_analysis import DiagnosticAnalysis

class AnalysisFactory:
    @staticmethod
    def get_analyzer(analysis_type: str):
        if analysis_type == "output_analysis":
            return OutputAnalysis
        elif analysis_type == "diagnostic_analysis":
            return DiagnosticAnalysis
        else:
            raise ValueError(f"Unknown analysis type: {analysis_type}")
