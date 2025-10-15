"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

===========================================================================
AnalysisFactory is a utility class that provides a centralized mechanism for retrieving
the appropriate analysis class based on the specified analysis type. It supports rule-based
output and diagnostic analysis modules used in test scenario evaluation.

Features:
- Maps analysis type strings to corresponding analysis classes.
- Supports extensibility for future analysis types.
- Raises descriptive errors for unsupported types.

Classes:
    AnalysisFactory:
        Provides a static method to retrieve analysis classes by type.

Supported Analysis Types:
    - "output_analysis": Returns OutputAnalysis class.
    - "diagnostic_analysis": Returns DiagnosticAnalysis class.

Usage:
    Call `AnalysisFactory.get_analyzer("output_analysis")` to retrieve the appropriate class.
    Instantiate the returned class with rules and optional step ID.
===========================================================================
"""

from analysis.output_analysis import OutputAnalysis
from analysis.diagnostic_analysis import DiagnosticAnalysis
from typing import Any, Type


class AnalysisFactory:
    @staticmethod
    def get_analyzer(
        analysis_type: str,
    ) -> Type[OutputAnalysis] | Type[DiagnosticAnalysis]:
        """
        Factory method to get the appropriate analysis class based on the analysis type.

        Args:
            analysis_type (str): The type of analysis ("output_analysis" or "diagnostic_analysis").
        Returns:
            class: The corresponding analysis class.
        Raises:
            ValueError: If the analysis type is unknown.
        """
        if analysis_type == "output_analysis":
            return OutputAnalysis
        elif analysis_type == "diagnostic_analysis":
            return DiagnosticAnalysis
        else:
            raise ValueError(f"Unknown analysis type: {analysis_type}")
