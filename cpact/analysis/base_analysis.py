"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

===========================================================================
BaseAnalysis is an abstract base class for implementing rule-based analysis modules
within the test execution framework. It provides a common interface and logging setup
for derived classes such as OutputAnalysis and DiagnosticAnalysis.

Features:
- Stores analysis rules and step context.
- Provides centralized logging via TestLogger.
- Defines an abstract `analyze()` method for custom analysis logic.
- Designed to be extended by specific analysis implementations.

Classes:
    BaseAnalysis:
        Abstract class for rule-based output and diagnostic analysis.

Usage:
    Subclass BaseAnalysis and implement the `analyze(output, context)` method.
    Use `rules` to define matching criteria and `step_id` for context tracking.
===================================================================
"""

from abc import ABC, abstractmethod
from typing import Any, Type

from utils.logger_utils import TestLogger
from core.context import Context


class BaseAnalysis(ABC):
    def __init__(self, rules: list[dict], step_id: str | None) -> None:
        """
        Initialize the analysis with given rules and optional step ID.
        Args:
            rules (list): A list of analysis rules or criteria.
            step_id (str, optional): An identifier for the step being analyzed. Defaults to None.
        Returns:
            None
        """
        self.rules = rules
        self.step_id = step_id
        self.logger = TestLogger().get_logger()

    @abstractmethod
    def analyze(self, output: Any, context: Type[Context]) -> list:
        """
        Analyze the given output based on the initialized rules and context.
        """
        pass
