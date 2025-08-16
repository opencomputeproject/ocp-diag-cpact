"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.
"""

from abc import ABC, abstractmethod

from utils.logger_utils import TestLogger

class BaseAnalysis(ABC):
    def __init__(self, rules: list):
        """
        Initialize the analysis with a set of rules.
        :param rules: List of rules to apply during analysis.
        """
        self.rules = rules
        self.logger = TestLogger().get_logger()

    @abstractmethod
    def analyze(self, output: str, context) -> list:
        """
        Analyze the output and update context if needed.
        Returns a list of results or findings.
        """
        pass
