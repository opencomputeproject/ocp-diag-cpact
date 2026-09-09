from __future__ import annotations

import re
from typing import Any, List, Tuple

from cpact.core.scenario_adapter import ScenarioAdapter


Condition = Tuple[str, str, str]


class RecipeFilter:
    """Filter v0.9 recipes by recipe_metadata properties."""

    _OPERATORS = (">=", "<=", "!=", "~", "*", ">", "<", "=")

    def __init__(self) -> None:
        self.groups: List[List[Condition]] = []

    def add_filter(self, filter_spec: str) -> None:
        or_group: List[Condition] = []
        for raw_condition in [part.strip() for part in filter_spec.split("|") if part.strip()]:
            or_group.append(self._parse_condition(raw_condition))
        if or_group:
            self.groups.append(or_group)

    def _parse_condition(self, condition: str) -> Condition:
        for operator in self._OPERATORS:
            if operator in condition:
                left, right = condition.split(operator, 1)
                return left.strip(), operator, right.strip()
        raise ValueError(f"Unsupported recipe filter format: {condition}")

    def matches(self, adapter: ScenarioAdapter) -> bool:
        if adapter.get_schema_version() != "0.9":
            return False
        if not self.groups:
            return True
        return all(any(self._matches_condition(adapter, *condition) for condition in group) for group in self.groups)

    def _matches_condition(self, adapter: ScenarioAdapter, property_name: str, operator: str, expected: str) -> bool:
        actual = adapter.get_property(property_name)
        if actual is None:
            return False
        if isinstance(actual, list):
            actual_text = " ".join(str(item) for item in actual)
        else:
            actual_text = str(actual)

        if operator == "=":
            return actual_text.lower() == expected.lower()
        if operator == "!=":
            return actual_text.lower() != expected.lower()
        if operator == "~":
            return bool(re.search(expected, actual_text))
        if operator == "*":
            return expected.lower().strip("*") in actual_text.lower()
        return self._compare_numeric(actual, operator, expected)

    def _compare_numeric(self, actual: Any, operator: str, expected: str) -> bool:
        actual_value = float(actual)
        expected_value = float(expected)
        if operator == ">=":
            return actual_value >= expected_value
        if operator == "<=":
            return actual_value <= expected_value
        if operator == ">":
            return actual_value > expected_value
        if operator == "<":
            return actual_value < expected_value
        raise ValueError(f"Unsupported operator: {operator}")
