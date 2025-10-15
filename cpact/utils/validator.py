"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

===============================================================================
validator.py

This module provides a flexible and extensible `Validator` class for performing
content validation between expected and actual data structures. It supports
multiple matching strategies including:

- Substring and token-based matching
- Regular expression matching
- Dictionary and JSON substructure matching
- List, tuple, and set element matching
- Fuzzy matching using similarity scores

The `Validator.search()` method serves as the entry point for recursive matching
across various data types, enabling robust validation logic for testing, data
comparison, and content verification workflows.

Example usage:
    Validator.search("expected text", "actual content", use_regex=True, use_fuzzy=True)
===============================================================================
"""
import re
from difflib import SequenceMatcher
from typing import Any, Tuple, Union


class Validator:
    """
    A utility class for searching expected content in actual content of any type.
    Supports:
    - Substring match
    - Token/word match
    - Regex match
    - Dict/JSON key-value or sub-dict match
    - List/tuple/set element match
    - Fuzzy match (optional)
    """

    @staticmethod
    def search(
        expected: Any,
        actual: Any,
        use_regex: bool = True,
        use_fuzzy: bool = False,
        fuzzy_threshold: float = 0.8,
    ) -> Tuple[bool, str]:
        """
        Perform a generic search between expected and actual data.

        Args:
            expected (Any): The expected value or structure.
            actual (Any): The actual value or structure.
            use_regex (bool): Enable regex matching if expected is a string.
            use_fuzzy (bool): Enable fuzzy matching for loose similarity.
            fuzzy_threshold (float): Minimum score for fuzzy match (0 to 1).

        Returns:
            Tuple[bool, str]: (match_found, reason_message)
        """
        return Validator._search_recursive(
            expected, actual, use_regex, use_fuzzy, fuzzy_threshold
        )

    @staticmethod
    def _search_recursive(
        expected: Any,
        actual: Any,
        use_regex: bool,
        use_fuzzy: bool,
        fuzzy_threshold: float,
    ) -> Tuple[bool, str]:
        """
        Recursively search for expected inside actual.

        Handles all data types: str, list, tuple, set, dict, etc.
        """
        if isinstance(expected, str) and isinstance(actual, str):
            return Validator._match_text(
                expected, actual, use_regex, use_fuzzy, fuzzy_threshold
            )

        if isinstance(expected, str) and isinstance(actual, (list, tuple, set)):
            for item in actual:
                match, reason = Validator._search_recursive(
                    expected, item, use_regex, use_fuzzy, fuzzy_threshold
                )
                if match:
                    return True, f"Matched in iterable: {reason}"
            return False, "No match in iterable"

        if isinstance(expected, str) and isinstance(actual, dict):
            for key, val in actual.items():
                if isinstance(key, str):
                    match, reason = Validator._search_recursive(
                        expected, key, use_regex, use_fuzzy, fuzzy_threshold
                    )
                    if match:
                        return True, f"Matched in dict key: {reason}"
                match, reason = Validator._search_recursive(
                    expected, val, use_regex, use_fuzzy, fuzzy_threshold
                )
                if match:
                    return True, f"Matched in dict value: {reason}"
            return False, "No match in dict"

        if isinstance(expected, dict) and isinstance(actual, dict):
            return Validator._match_dict(
                expected, actual, use_regex, use_fuzzy, fuzzy_threshold
            )

        if isinstance(expected, dict) and isinstance(actual, list):
            for item in actual:
                if isinstance(item, dict):
                    match, reason = Validator._match_dict(
                        expected, item, use_regex, use_fuzzy, fuzzy_threshold
                    )
                    if match:
                        return True, f"Matched sub-dict in list: {reason}"
            return False, "No sub-dict match in list"

        if isinstance(expected, (list, tuple, set)):
            for item in expected:
                match, reason = Validator._search_recursive(
                    item, actual, use_regex, use_fuzzy, fuzzy_threshold
                )
                if match:
                    return True, f"Matched item from expected iterable: {reason}"
            return False, "No match from expected iterable"

        if expected == actual:
            return True, "Exact match"

        return False, "Expected and actual values do not match"

    @staticmethod
    def _match_text(
        expected: str,
        actual: str,
        use_regex: bool,
        use_fuzzy: bool,
        fuzzy_threshold: float,
    ) -> Tuple[bool, str]:
        """
        Matches two strings using regex, substring, word tokens, or fuzzy matching.

        Returns:
            Tuple[bool, str]: (match_found, reason_message)
        """
        expected = expected.strip()
        actual = actual.strip()

        # Regex match
        if use_regex:
            try:
                if re.search(expected, actual):
                    return True, f"Regex matched: `{expected}`"
            except re.error:
                pass  # Invalid regex

        # Substring match
        if expected in actual:
            return True, "Substring matched"

        # Word/token match
        expected_tokens = set(expected.lower().split())
        actual_tokens = set(actual.lower().split())
        if expected_tokens.issubset(actual_tokens):
            return True, "Token match"

        # Fuzzy match
        if use_fuzzy:
            score = SequenceMatcher(None, expected.lower(), actual.lower()).ratio()
            if score >= fuzzy_threshold:
                return True, f"Fuzzy match with score {score:.2f}"

        return False, "Expected and actual strings do not match"

    @staticmethod
    def _match_dict(
        expected: dict,
        actual: dict,
        use_regex: bool,
        use_fuzzy: bool,
        fuzzy_threshold: float,
    ) -> Tuple[bool, str]:
        """
        Matches whether the expected dict is a sub-dict of the actual dict.

        Returns:
            Tuple[bool, str]: (match_found, reason_message)
        """
        for key, val in expected.items():
            if key not in actual:
                return False, f"Key '{key}' not found in actual"
            match, reason = Validator._search_recursive(
                val, actual[key], use_regex, use_fuzzy, fuzzy_threshold
            )
            if not match:
                return False, f"Value mismatch for key '{key}': {reason}"
        return True, "Sub-dict matched"
