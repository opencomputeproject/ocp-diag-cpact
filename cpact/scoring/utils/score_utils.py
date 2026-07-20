"""
Console color formatting utilities for CPACT scoring reports.

Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This module provides reusable ANSI color helpers used by the CPACT scoring
presentation layer to improve the readability of console reports. It centralizes
terminal color formatting logic so report-rendering components can present
consistent visual output without duplicating ANSI escape sequence handling.

Supported features:
    - Status-based color formatting (PASS, FAIL, PARTIAL)
    - Score-based color formatting using configurable thresholds
    - Highlighted report headings and titles
    - Consistent ANSI styling across CPACT scoring reports
"""

from __future__ import annotations


class ReportColor:
    """ANSI color formatting helpers for CPACT console reports."""

    RESET = "\033[0m"

    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"

    _STATUS_COLORS = {
        "PASS": GREEN,
        "FAIL": RED,
        "PARTIAL": YELLOW,
    }

    @classmethod
    def status(cls, status: str) -> str:
        """Return a colorized validation status.

        Args:
            status: Validation status string.

        Returns:
            The ANSI-colored status if recognized; otherwise, the original
            status text.
        """
        normalized = status.upper()
        color = cls._STATUS_COLORS.get(normalized)

        if color is None:
            return normalized

        return f"{color}{normalized}{cls.RESET}"

    @classmethod
    def score(cls, score: float) -> str:
        """Return a colorized score.

        Scores are colored using the following thresholds:
            - Green: 90 and above
            - Yellow: 70 to <90
            - Red: Below 70

        Args:
            score: Numeric score.

        Returns:
            ANSI-colored score formatted to two decimal places.
        """
        if score >= 90:
            color = cls.GREEN
        elif score >= 70:
            color = cls.YELLOW
        else:
            color = cls.RED

        return f"{color}{score:.2f}{cls.RESET}"

    @classmethod
    def heading(cls, text: str) -> str:
        """Return a cyan-colored report heading."""
        return f"{cls.CYAN}{text}{cls.RESET}"

    @classmethod
    def title(cls, text: str) -> str:
        """Return a blue-colored report title."""
        return f"{cls.BLUE}{text}{cls.RESET}"