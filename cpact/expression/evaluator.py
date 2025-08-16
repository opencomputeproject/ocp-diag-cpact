"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.
"""

import operator
from utils.logger_utils import TestLogger

class ExpressionEvaluator:
    def __init__(self, context):
        self.logger = TestLogger().get_logger()
        self.context = context
        self.operators = {
            'and': operator.and_,
            'or': operator.or_,
            'not': operator.not_,
            '==': operator.eq,
            '!=': operator.ne,
            '>': operator.gt,
            '>=': operator.ge,
            '<': operator.lt,
            '<=': operator.le
        }

    def evaluate(self, entry_criteria, diagnostic_keys):
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

    def _evaluate_single(self, entry_criteria, diagnostic_keys):
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

    # def _eval(self, tokens):
    #     if not tokens:
    #         return True

    #     token = tokens.pop(0)
    #     if token == "(":
    #         result = self._eval(tokens)
    #         tokens.pop(0)  # remove ")"
    #         return result
    #     elif token in self.operators:
    #         if token == "not":
    #             return self.operators[token](self._eval(tokens))
    #         left = self._eval(tokens)
    #         right = self._eval(tokens)
    #         return self.operators[token](left, right)
    #     # elif token in self.context.vars:
    #     #     return self.context.get(token)
    #     elif token.lower() in ["true", "false"]:
    #         return token.lower() == "true"
    #     elif token.isdigit():
    #         return int(token)
    #     else:
    #         return token
