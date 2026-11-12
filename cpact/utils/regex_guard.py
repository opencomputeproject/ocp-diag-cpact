"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.
This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

===============================================================================
Limits for regular expressions supplied by recipes (diagnostic/output analysis,
expected_output, JSON patterns).

Python's ``re`` has no match timeout, so this module bounds the risk instead:

- patterns longer than ``MAX_PATTERN_LENGTH`` are rejected;
- patterns with a quantified group that itself contains a quantifier (the
  classic catastrophic-backtracking shape, e.g. ``(a+)+``) are logged as a
  warning;
- inputs larger than the analysis limit fail the step instead of being
  silently truncated (``CPACT_MAX_ANALYSIS_MB``, default 256);
- matches that take longer than ``SLOW_MATCH_SECONDS`` are logged.
===============================================================================
"""

from __future__ import annotations

import functools
import logging
import os
import re
import time
from contextlib import contextmanager
from typing import Iterator

MAX_PATTERN_LENGTH = 4096
DEFAULT_MAX_ANALYSIS_MB = 256
ENV_MAX_ANALYSIS_MB = "CPACT_MAX_ANALYSIS_MB"
SLOW_MATCH_SECONDS = 5.0

# A group containing + or * that is itself followed by +, * or {n,}.
_NESTED_QUANTIFIER_RE = re.compile(
    r"\((?:[^()\\]|\\.)*[+*](?:[^()\\]|\\.)*\)(?:[+*]|\{\d*,\d*\})"
)

_logger = logging.getLogger("test_logger")


class RegexLimitError(ValueError):
    """Raised when a recipe regex or its input exceeds the configured limits."""


def max_analysis_chars() -> int:
    """Largest input (in characters) that recipe regexes may be run over."""
    raw = os.environ.get(ENV_MAX_ANALYSIS_MB, "")
    try:
        mb = float(raw) if raw.strip() else DEFAULT_MAX_ANALYSIS_MB
    except ValueError:
        mb = DEFAULT_MAX_ANALYSIS_MB
    return int(mb * 1024 * 1024)


@functools.lru_cache(maxsize=512)
def compile_recipe_regex(pattern: str, flags: int = 0) -> "re.Pattern[str]":
    """Compile a recipe-supplied regex after applying the length/shape checks."""
    if not isinstance(pattern, str):
        raise RegexLimitError(f"Regex must be a string, got {type(pattern).__name__}")
    if len(pattern) > MAX_PATTERN_LENGTH:
        raise RegexLimitError(
            f"Regex is {len(pattern)} characters long; the limit is {MAX_PATTERN_LENGTH}"
        )
    if _NESTED_QUANTIFIER_RE.search(pattern):
        _logger.warning(
            f"Regex {pattern[:200]!r} has a nested quantifier and may backtrack "
            "catastrophically on large inputs; consider making it more specific."
        )
    try:
        return re.compile(pattern, flags)
    except re.error as exc:
        raise RegexLimitError(f"Invalid regex {pattern[:200]!r}: {exc}") from exc


def check_input_size(text: object, what: str = "input") -> None:
    """Fail (rather than truncate) when ``text`` is too large to analyse safely."""
    size = len(text) if isinstance(text, (str, bytes)) else 0
    limit = max_analysis_chars()
    if size > limit:
        raise RegexLimitError(
            f"{what} is {size} characters, above the {limit // (1024 * 1024)} MB analysis "
            f"limit; set {ENV_MAX_ANALYSIS_MB} to analyse larger inputs"
        )


def check_file_size(path: str, what: str = "file") -> None:
    """Like :func:`check_input_size`, but checked before reading a file."""
    size = os.path.getsize(path)
    limit = max_analysis_chars()
    if size > limit:
        raise RegexLimitError(
            f"{what} '{path}' is {size} bytes, above the {limit // (1024 * 1024)} MB analysis "
            f"limit; set {ENV_MAX_ANALYSIS_MB} to analyse larger files"
        )


@contextmanager
def timed_match(description: str) -> Iterator[None]:
    """Log a warning when a regex evaluation is unexpectedly slow."""
    start = time.monotonic()
    try:
        yield
    finally:
        elapsed = time.monotonic() - start
        if elapsed > SLOW_MATCH_SECONDS:
            _logger.warning(f"Slow regex evaluation ({elapsed:.1f}s): {description[:200]}")
