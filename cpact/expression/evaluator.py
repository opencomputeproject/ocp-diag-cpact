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
- Evaluates entry criteria expressions with a restricted AST interpreter
  (never Python's eval), so recipes cannot execute arbitrary code.
- Supports logical and comparison operators (and, or, not, ==, !=, >, >=, <, <=,
  in, not in, is, is not), literals, numeric arithmetic (+, -, *, /, //, %) and
  indexing. Attribute access, function calls and other syntax are rejected.
- Logs evaluation results and errors for traceability.
- Designed to work with diagnostic key-value pairs and scenario context.
- Provides fallback handling for missing or malformed expressions.

Classes:
    ExpressionEvaluator:
        Evaluates expressions defined in scenario entry criteria using diagnostic context.

Usage:
    Instantiate ExpressionEvaluator with a context object.
    Call `evaluate(entry_criteria, diagnostic_keys)` to validate criteria.
    Expressions use Python expression syntax referencing keys in `diagnostic_keys`.
===========================================================================
"""

import ast
import operator
from typing import Any, Mapping, Union, Type
from cpact.utils.logger_utils import TestLogger
from cpact.core.context import Context
from cpact.utils.custom_exception_handler import CustomExceptionHandler


class UnsafeExpressionError(ValueError):
    """Raised when an expression uses syntax outside the allowed subset."""


_MAX_EXPRESSION_LENGTH = 2000

_COMPARE_OPS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
    ast.Is: operator.is_,
    ast.IsNot: operator.is_not,
}

_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
}

_UNARY_OPS = {
    ast.Not: operator.not_,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def safe_eval(expression: str, names: Mapping[str, Any]) -> Any:
    """
    Evaluate an entry-criteria expression without using Python's eval.

    Only names from ``names``, literals, boolean/comparison operators, numeric
    arithmetic and indexing are allowed; anything else raises
    UnsafeExpressionError. Unknown names raise NameError, matching eval().
    """
    if not isinstance(expression, str):
        raise UnsafeExpressionError("Expression must be a string")
    if len(expression) > _MAX_EXPRESSION_LENGTH:
        raise UnsafeExpressionError(
            f"Expression longer than {_MAX_EXPRESSION_LENGTH} characters"
        )
    tree = ast.parse(expression.strip(), mode="eval")
    return _eval_node(tree.body, names or {})


def _eval_node(node: ast.AST, names: Mapping[str, Any]) -> Any:
    if isinstance(node, ast.Constant):
        return node.value

    if isinstance(node, ast.Name):
        if node.id in names:
            return names[node.id]
        raise NameError(f"name '{node.id}' is not defined")

    if isinstance(node, ast.BoolOp):
        # Short-circuit with Python semantics (returns the deciding operand).
        is_and = isinstance(node.op, ast.And)
        value = None
        for operand in node.values:
            value = _eval_node(operand, names)
            if is_and and not value:
                return value
            if not is_and and value:
                return value
        return value

    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        operand = _eval_node(node.operand, names)
        if not isinstance(node.op, ast.Not):
            _require_number(operand)
        return _UNARY_OPS[type(node.op)](operand)

    if isinstance(node, ast.Compare):
        left = _eval_node(node.left, names)
        for op, comparator in zip(node.ops, node.comparators):
            right = _eval_node(comparator, names)
            if not _COMPARE_OPS[type(op)](left, right):
                return False
            left = right
        return True

    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        left = _eval_node(node.left, names)
        right = _eval_node(node.right, names)
        # Numbers only: blocks e.g. "x" * 10**9 memory blow-ups via sequences.
        _require_number(left)
        _require_number(right)
        return _BIN_OPS[type(node.op)](left, right)

    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        items = [_eval_node(elt, names) for elt in node.elts]
        if isinstance(node, ast.Tuple):
            return tuple(items)
        if isinstance(node, ast.Set):
            return set(items)
        return items

    if isinstance(node, ast.Subscript) and not isinstance(node.slice, ast.Slice):
        container = _eval_node(node.value, names)
        if not isinstance(container, (dict, list, tuple, str)):
            raise UnsafeExpressionError(
                f"Indexing is not supported on {type(container).__name__}"
            )
        return container[_eval_node(node.slice, names)]

    raise UnsafeExpressionError(
        f"Unsupported syntax in expression: {type(node).__name__}"
    )


def _require_number(value: Any) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise UnsafeExpressionError(
            f"Arithmetic is only supported on numbers, got {type(value).__name__}"
        )


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
            result = safe_eval(expression, diagnostic_keys)
            self.logger.info(f"[Expression] '{expression}' => {result}")
            return result
        except Exception as e:
            CustomExceptionHandler.print_exception(e)
            self.logger.error(f"Failed to evaluate expression '{expression}': {e}")
            return False
