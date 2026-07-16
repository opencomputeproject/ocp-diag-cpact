"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.
================================================================================

Provides console color formatting utilities for CPACT scoring reports.

This module defines reusable ANSI color helpers used by the CPACT scoring
presentation layer to improve readability of validation statuses, score values,
headings, and report titles. The utilities centralize terminal color formatting
logic so report-rendering components can present consistent visual output
without duplicating ANSI escape sequence handling.

The module supports:
- Status-based color formatting for PASS, FAIL, and PARTIAL outcomes.
- Score-based color formatting using configurable score thresholds.
- Highlighted headings and titles for console reports.
- Consistent terminal output styling across scoring reports.

Classes:
    ReportColor:
        Utility class containing ANSI color constants and helper methods for
        formatting report text, statuses, and scores.

Design Goals:
    - Centralize console color formatting logic.
    - Improve readability of scoring and validation output.
    - Keep presentation helpers lightweight and reusable.
    - Maintain consistent report styling across CPACT scoring components.

Implementation follows PEP 257 documentation conventions and aligns with
CPACT framework coding standards.
"""

class ReportColor:

    RESET = "\033[0m"

    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"

    @classmethod
    def status(cls, status):

        status = status.upper()

        if status == "PASS":
            return f"{cls.GREEN}{status}{cls.RESET}"

        if status == "FAIL":
            return f"{cls.RED}{status}{cls.RESET}"

        if status == "PARTIAL":
            return f"{cls.YELLOW}{status}{cls.RESET}"

        return status

    @classmethod
    def score(cls, score):

        if score >= 90:
            return f"{cls.GREEN}{score:.2f}{cls.RESET}"

        elif score >= 70:
            return f"{cls.YELLOW}{score:.2f}{cls.RESET}"

        return f"{cls.RED}{score:.2f}{cls.RESET}"

    @classmethod
    def heading(cls, text):
        return f"{cls.CYAN}{text}{cls.RESET}"

    @classmethod
    def title(cls, text):
        return f"{cls.BLUE}{text}{cls.RESET}"