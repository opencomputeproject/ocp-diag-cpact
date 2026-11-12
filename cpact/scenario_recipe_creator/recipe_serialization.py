"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.


This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

===============================================================================
Qt-free serialization helpers for the scenario recipe creator.

These turn the data held by the editor widgets into plain, YAML/JSON-safe
structures: sanitizing values, normalizing list-shaped step fields
(entry_criteria, output_analysis, diagnostic_analysis) and applying the
per-step-type field rules. Extracted from RecipeCreator so they can be tested
and reused without a GUI.
===============================================================================
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple

_PRIMITIVES = (str, int, float, bool, type(None))


def sanitize(obj: Any) -> Any:
    """Recursively make ``obj`` serializable: string dict keys, unknown objects -> str."""
    if isinstance(obj, dict):
        return {str(k): sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize(v) for v in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)


def flatten_once(lst: Any) -> Any:
    """Flatten one level of nested lists; non-lists are returned unchanged."""
    if not isinstance(lst, list):
        return lst
    out = []
    for el in lst:
        if isinstance(el, list):
            out.extend(el)
        else:
            out.append(el)
    return out


def normalize_item_list(value: Any) -> List[Dict[str, Any]]:
    """
    Normalize a list-of-dicts step field (entry_criteria, output_analysis,
    diagnostic_analysis): None -> [], a dict -> [dict], a (nested) list ->
    flattened once with non-dict items wrapped as {"value": item}.
    """
    if value is None:
        return []
    value = sanitize(value)
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [item if isinstance(item, dict) else {"value": item} for item in flatten_once(value)]
    return []


def normalize_step(step: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Sanitize a step and apply the step-type rules:
    command_execution has no diagnostic_analysis, log_analysis has no
    output_analysis, invoke_scenario has neither; list fields are only kept
    when allowed and non-empty (entry_criteria is always normalized).
    """
    step = sanitize(step or {})
    step["entry_criteria"] = normalize_item_list(step.get("entry_criteria", []))

    step_type = (step.get("step_type") or "").strip().lower()
    normalized_output = normalize_item_list(step.get("output_analysis", []))
    normalized_diag = normalize_item_list(step.get("diagnostic_analysis", []))

    is_command = step_type == "command_execution"
    is_log = step_type == "log_analysis"
    is_invoke = step_type == "invoke_scenario"

    if is_command:
        step.pop("diagnostic_analysis", None)
    if is_log:
        step.pop("output_analysis", None)
    if is_invoke:
        step.pop("diagnostic_analysis", None)
        step.pop("output_analysis", None)

    if not is_log and not is_invoke and normalized_output:
        step["output_analysis"] = normalized_output
    if not is_command and not is_invoke and normalized_diag:
        step["diagnostic_analysis"] = normalized_diag
    return step


def find_first_nonprimitive(obj: Any, path: str = "root") -> Optional[Tuple[str, Any, type]]:
    """Return ``(path, obj, type)`` of the first non-primitive leaf, or None (export diagnostics)."""
    if isinstance(obj, _PRIMITIVES):
        return None
    if isinstance(obj, (dict, OrderedDict)):
        for k, v in dict(obj).items():
            res = find_first_nonprimitive(v, f"{path}['{k}']")
            if res:
                return res
        return None
    if isinstance(obj, (list, tuple)):
        for idx, v in enumerate(obj):
            res = find_first_nonprimitive(v, f"{path}[{idx}]")
            if res:
                return res
        return None
    return (path, obj, type(obj))
