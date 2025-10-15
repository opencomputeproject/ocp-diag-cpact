"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

===========================================================================
ExpressionEvaluator is a utility class for evaluating logical expressions against
diagnostic context keys in automated test scenarios. It supports dynamic expression
parsing and integrates with a shared context and centralized logging system.

Features:
- Evaluates entry criteria expressions using Python's eval.
- Supports logical and comparison operators (and, or, not, ==, !=, >, >=, <, <=).
- Logs evaluation results and errors for traceability.
- Designed to work with diagnostic key-value pairs and scenario context.
- Provides fallback handling for missing or malformed expressions.

Classes:
    ExpressionEvaluator:
        Evaluates expressions defined in scenario entry criteria using diagnostic context.

Usage:
    Instantiate ExpressionEvaluator with a context object.
    Call `evaluate(entry_criteria, diagnostic_keys)` to validate criteria.
    Expressions should be valid Python syntax referencing keys in `diagnostic_keys`.
===========================================================================
"""

import operator
from typing import Union, List, Dict, Type
from utils.logger_utils import TestLogger
from core.context import Context


class ExpressionEvaluator:
    def __init__(self, context: Type[Context]) -> None:
        """
        Initializes the ExpressionEvaluator with a context for variable resolution.
        Args:
            context (Context): The shared context for storing and managing data.
        Returns:
            None
        """
        self.logger = TestLogger().get_logger()
        self.context = context
        self.operators = {
            "and": operator.and_,
            "or": operator.or_,
            "not": operator.not_,
            "==": operator.eq,
            "!=": operator.ne,
            ">": operator.gt,
            ">=": operator.ge,
            "<": operator.lt,
            "<=": operator.le,
        }

    def evaluate(
        self, entry_criteria: Union[list, dict], diagnostic_keys: dict
    ) -> bool:
        """
        Evaluates the entry criteria against the provided diagnostic keys.
        Args:
            entry_criteria (list or dict): The entry criteria to be evaluated.
            diagnostic_keys (dict): The diagnostic keys to be used in the evaluation.
        Returns:
            bool: True if all criteria are met, False otherwise.
        """
        results = []
        for criteria in entry_criteria:
            if not self._evaluate_single(criteria, diagnostic_keys):
                self.logger.info(f"Entry criteria '{criteria}' not met. Skipping step.")
                # return False
                results.append(False)
            results.append(True)
        if len(results) == 1:
            return results[0]
        return all(results)

    def _evaluate_single(
        self, entry_criteria: Union[list, dict], diagnostic_keys: dict
    ) -> bool:
        """
        Evaluates a single entry criteria against the provided diagnostic keys.
        Args:
            entry_criteria (dict): The entry criteria to be evaluated.
            diagnostic_keys (dict): The diagnostic keys to be used in the evaluation.
        Returns:
            bool: True if the criteria is met, False otherwise.
        """
        expression = entry_criteria.get("expression")
        if not expression:
            self.logger.warning("No expression provided for evaluation.")
            return False
        try:
            result = eval(expression, {}, diagnostic_keys)
            self.logger.info(f"[Expression] '{expression}' => {result}")
            return result
        except Exception as e:
            self.logger.error(f"Failed to evaluate expression '{expression}': {e}")
            return False
