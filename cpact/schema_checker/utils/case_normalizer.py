"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

===============================================================================
Case normalization helpers for schema validation.

Connection identifiers (``connection``, ``connection_type`` and their plural
config counterparts ``connections`` / ``connection_types``) are validated
case-insensitively. Both the document under test and the JSON schema are
copied and only the values of those keys (data) and the ``enum`` / ``const``
constraints beneath those properties (schema) are lowercased. All other
fields remain case-sensitive and the original objects are never mutated.
===============================================================================
"""

from collections.abc import Mapping
from typing import Any

CASE_INSENSITIVE_KEYS = frozenset(
    {"connection", "connection_type", "connections", "connection_types"}
)


def _lower(value: Any) -> Any:
    return value.lower() if isinstance(value, str) else value


def _copy_plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {k: _copy_plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_copy_plain(v) for v in value]
    return value


def normalize_data(data: Any) -> Any:
    """
    Return a plain-dict/list copy of ``data`` with the values of
    case-insensitive keys lowercased (strings, or strings inside lists).
    """
    if isinstance(data, Mapping):
        result = {}
        for key, value in data.items():
            if key in CASE_INSENSITIVE_KEYS:
                if isinstance(value, (list, tuple)):
                    result[key] = [_lower(_copy_plain(v)) for v in value]
                else:
                    result[key] = _lower(_copy_plain(value))
            else:
                result[key] = normalize_data(value)
        return result
    if isinstance(data, (list, tuple)):
        return [normalize_data(v) for v in data]
    return data


def _lower_constraints(schema: Any) -> Any:
    """Lowercase every string ``enum`` member and ``const`` in a sub-schema."""
    if isinstance(schema, Mapping):
        result = {}
        for key, value in schema.items():
            if key == "enum" and isinstance(value, list):
                result[key] = [_lower(v) for v in value]
            elif key == "const":
                result[key] = _lower(value)
            else:
                result[key] = _lower_constraints(value)
        return result
    if isinstance(schema, (list, tuple)):
        return [_lower_constraints(v) for v in schema]
    return schema


def normalize_schema(schema: Any) -> Any:
    """
    Return a copy of ``schema`` where ``enum`` / ``const`` values declared
    under case-insensitive properties are lowercased.
    """
    if isinstance(schema, Mapping):
        result = {}
        for key, value in schema.items():
            if key == "properties" and isinstance(value, Mapping):
                result[key] = {
                    prop: (
                        _lower_constraints(sub)
                        if prop in CASE_INSENSITIVE_KEYS
                        else normalize_schema(sub)
                    )
                    for prop, sub in value.items()
                }
            else:
                result[key] = normalize_schema(value)
        return result
    if isinstance(schema, (list, tuple)):
        return [normalize_schema(v) for v in schema]
    return schema
