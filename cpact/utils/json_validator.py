#!/usr/bin/env python3

import json
import re
import argparse
from copy import deepcopy
from typing import Any

class JSONValidator:
    _instance = None

    def __new__(cls) -> "JSONValidator":
        if cls._instance is None:
            cls._instance = super(JSONValidator, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self) -> None:
        """
        Initializes the JSONValidator with a given schema.

        Args:
            schema (dict): The JSON schema to validate against.
        """

    
    def normalize_regex(self, pattern: str) -> str:
        """
        Convert regex patterns with named groups from (?<name>...) to (?P<name>...).

        Args:
            pattern (str): The regex pattern to normalize.
        Returns:
            str: The normalized regex pattern.
        """
        return re.sub(r"\(\?<(\w+)>", r"(?P<\1>", pattern)
    
    def match_regex(self, pattern: str, value: Any, groups: dict, ignore_case: bool = False) -> (bool, dict):
        """
        Match a regex pattern against a value and extract named groups.

        Args:
            pattern (str): The regex pattern to match.
            value (Any): The value to match against the pattern.
            groups (dict): A dictionary to store extracted groups.
            ignore_case (bool): Whether to ignore case in matching.
        Returns:
            (bool, dict): A tuple containing a boolean indicating if the match was successful and the updated groups dictionary.
        """
        flags = re.IGNORECASE if ignore_case else 0

        try:
            pattern = self.normalize_regex(pattern)
            regex = re.fullmatch(pattern, str(value), flags)
        except re.error:
            return (pattern == value, groups)

        if not regex:
            return (False, groups)

        new_groups = deepcopy(groups)
        new_groups.update({k: v for k, v in regex.groupdict().items() if v is not None})

        return (True, new_groups)
    
    def match_pattern(self, pattern: Any, data: Any, groups: dict = None, ignore_case: bool = False) -> list:
        """
        Recursively match a pattern against data, supporting dicts, lists, and values.

        Args:
            pattern (Any): The pattern to match, which can be a dict, list, or value.
            data (Any): The data to match against the pattern.
            groups (dict): A dictionary to store extracted groups during matching.
            ignore_case (bool): Whether to ignore case in matching.
        Returns:
            list: A list of dictionaries containing extracted groups for each successful match.
        """
        if groups is None:
            groups = {}

        results = []

        # ---- dict (AND + backtracking) ----
        if isinstance(pattern, dict):
            if not isinstance(data, dict):
                return []

            def backtrack(p_items, current_groups):
                if not p_items:
                    return [current_groups]

                p_key, p_val = p_items[0]
                rest = p_items[1:]

                matches = []

                for d_key, d_val in data.items():
                    key_match, new_groups = self.match_regex(
                        p_key, d_key, current_groups, ignore_case
                    )

                    if not key_match:
                        continue

                    sub_matches = self.match_pattern(
                        p_val, d_val, new_groups, ignore_case
                    )

                    for sm in sub_matches:
                        matches.extend(backtrack(rest, sm))

                return matches

            # match at current node
            results.extend(backtrack(list(pattern.items()), deepcopy(groups)))

            # search deeper (VERY IMPORTANT)
            for v in data.values():
                results.extend(self.match_pattern(pattern, v, deepcopy(groups), ignore_case))

            return results


        # ---- list ----
        elif isinstance(pattern, list):
            if not isinstance(data, list):
                return []

            results = []

            for item in data:
                # isolate each branch
                results.extend(
                    self.match_pattern(pattern[0], item, deepcopy(groups), ignore_case)
                )

            return results


        # ---- value ----
        else:
            if isinstance(pattern, str):
                matched, new_groups = self.match_regex(pattern, data, groups, ignore_case)
                return [new_groups] if matched else []
            else:
                return [groups] if pattern == data else []
