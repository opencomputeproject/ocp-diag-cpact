"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

===============================================================================
Secret redaction for logs and OCP-TV output.

Two layers are applied by ``redact()``:

1. Exact values registered at runtime (e.g. every password/token in the loaded
   connection config, via ``register_secrets_from_config``).
2. Generic patterns for credentials that commonly appear in commands and their
   output: ``password=...``, ``--password ...``, ``"token": "..."``,
   ``Authorization: Basic ...``, ``user:pass@host`` URLs, ``curl -u user:pass``,
   ``sshpass -p ...`` and ``ipmitool ... -P ...``.

``RedactingFilter`` applies this to every record on the CPACT logger, so
callers do not need to remember to redact individual log lines.
===============================================================================
"""

from __future__ import annotations

import logging
import re
import threading
import traceback
from typing import Any, List, Set

MASK = "***"

# Shorter values would mask too many unrelated substrings of normal output.
_MIN_SECRET_LENGTH = 4

_SECRET_KEY_RE = re.compile(
    r"(password|passwd|passphrase|secret|token|api[_-]?key|access[_-]?key|private[_-]?key)",
    re.IGNORECASE,
)

_registered: Set[str] = set()
_registered_sorted: List[str] = []
_lock = threading.Lock()

_SECRET_WORD = r"(?:password|passwd|passphrase|secret|token|api[_-]?key|access[_-]?key|auth[_-]?key)"
_QUOTED_OR_BARE = r"(?:\"(?:[^\"\\]|\\.)*\"|'[^']*'|[^\s\"'&,;]+)"

_PATTERNS = [
    # key=value / key: value / "key": "value" for secret-looking keys.
    # [ \t]* (not \s*) so a "Password:" prompt never swallows the next line.
    (
        re.compile(
            rf"(?i)([\"']?[\w.-]*{_SECRET_WORD}[\w.-]*[\"']?[ \t]*[:=][ \t]*)({_QUOTED_OR_BARE})"
        ),
        "kv",
    ),
    # --password value / --token=value style CLI flags.
    (
        re.compile(rf"(?i)(--?[\w-]*{_SECRET_WORD}[\w-]*[ \t]+)({_QUOTED_OR_BARE})"),
        "plain",
    ),
    # Authorization: Basic xxx / Bearer xxx
    (re.compile(r"(?i)(\b(?:basic|bearer)[ \t]+)([A-Za-z0-9._~+/=-]{8,})"), "plain"),
    # scheme://user:password@host
    (re.compile(r"(?i)(\b[a-z][a-z0-9+.-]*://[^/\s:@]+:)([^@\s/]+)(?=@)"), "plain"),
    # curl -u user:password / --user user:password
    (re.compile(r"((?:^|\s)(?:-u|--user)[ \t]+[^:\s]+:)(\S+)"), "plain"),
    # sshpass -p password
    (re.compile(r"(\bsshpass[ \t]+-p[ \t]*)(\S+)"), "plain"),
    # ipmitool ... -P password
    (re.compile(r"(\bipmitool\b[^\n]*?[ \t]-P[ \t]*)(\S+)"), "plain"),
]


def _mask_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return f"{value[0]}{MASK}{value[0]}"
    return MASK


def register_secret(value: Any) -> None:
    """Mask every future occurrence of ``value`` in logs."""
    global _registered_sorted
    if not isinstance(value, str):
        return
    value = value.strip()
    if len(value) < _MIN_SECRET_LENGTH:
        return
    with _lock:
        if value in _registered:
            return
        _registered.add(value)
        # Rebind (not mutate) so concurrent redact() calls iterate a stable list.
        _registered_sorted = sorted(_registered, key=len, reverse=True)


def register_secrets_from_config(config: Any) -> None:
    """Register the values of all secret-looking keys in a nested config."""
    if isinstance(config, dict):
        for key, value in config.items():
            if isinstance(key, str) and _SECRET_KEY_RE.search(key) and isinstance(value, str):
                register_secret(value)
            else:
                register_secrets_from_config(value)
    elif isinstance(config, (list, tuple)):
        for item in config:
            register_secrets_from_config(item)


def redact(text: Any) -> Any:
    """Return ``text`` with registered secrets and credential patterns masked."""
    if not isinstance(text, str) or not text:
        return text

    for secret in _registered_sorted:
        if secret in text:
            text = text.replace(secret, MASK)

    for pattern, kind in _PATTERNS:
        if kind == "kv":
            text = pattern.sub(lambda m: m.group(1) + _mask_value(m.group(2)), text)
        else:
            text = pattern.sub(lambda m: m.group(1) + MASK, text)
    return text


def redact_data(data: Any) -> Any:
    """Recursively redact strings in a JSON-like structure, masking secret keys."""
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            if isinstance(key, str) and _SECRET_KEY_RE.search(key) and isinstance(value, str) and value:
                result[key] = MASK
            else:
                result[key] = redact_data(value)
        return result
    if isinstance(data, list):
        return [redact_data(item) for item in data]
    if isinstance(data, str):
        return redact(data)
    return data


class RedactingFilter(logging.Filter):
    """Logging filter that redacts the formatted message and any traceback."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            return True
        redacted = redact(message)
        if redacted != message:
            record.msg = redacted
            record.args = None
        if record.exc_info and not record.exc_text:
            record.exc_text = redact(
                "".join(traceback.format_exception(*record.exc_info)).rstrip("\n")
            )
        return True
