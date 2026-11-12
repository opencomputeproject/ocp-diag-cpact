"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

===============================================================================
Confinement of file paths that come from recipes (scenario_path,
log_analysis_path, expected_output_path, map_file).

A recipe path is accepted only if, after resolving ``..`` and symlinks, it lies
inside one of the allowed roots:

- the roots configured by the CLI (working directory, --workspace, --test_dir,
  the run's log directory and every --allowed_path),
- extra roots from the ``CPACT_ALLOWED_PATHS`` environment variable
  (``os.pathsep``-separated),
- the folder of the recipe that references the path.

When nothing has been configured (library use), the working directory is the
only default root.
===============================================================================
"""

from __future__ import annotations

import os
import re
import threading
from typing import Iterable, List, Optional

ENV_ALLOWED_PATHS = "CPACT_ALLOWED_PATHS"

_lock = threading.Lock()
_configured_roots: Optional[List[str]] = None


class PathNotAllowedError(ValueError):
    """Raised when a recipe path resolves outside every allowed root."""


def _normalize_root(path: str) -> str:
    return os.path.realpath(os.path.abspath(os.path.expanduser(str(path))))


def _env_roots() -> List[str]:
    raw = os.environ.get(ENV_ALLOWED_PATHS, "")
    return [_normalize_root(p) for p in raw.split(os.pathsep) if p.strip()]


def _dedupe(paths: Iterable[str]) -> List[str]:
    seen, result = set(), []
    for path in paths:
        key = os.path.normcase(path)
        if key not in seen:
            seen.add(key)
            result.append(path)
    return result


def configure_allowed_roots(roots: Iterable[Optional[str]]) -> List[str]:
    """Set the run-wide allowed roots (empty/None entries are ignored)."""
    global _configured_roots
    normalized = _dedupe(_normalize_root(r) for r in roots if r)
    with _lock:
        _configured_roots = normalized
    return list(normalized)


def reset_allowed_roots() -> None:
    """Forget configured roots (falls back to the working directory)."""
    global _configured_roots
    with _lock:
        _configured_roots = None


def allowed_roots(recipe_path: Optional[str] = None) -> List[str]:
    """Return the effective allowed roots, including the recipe's own folder."""
    with _lock:
        base = list(_configured_roots) if _configured_roots is not None else [_normalize_root(os.getcwd())]
    roots = base + _env_roots()
    if recipe_path:
        roots.append(_normalize_root(os.path.dirname(os.path.abspath(str(recipe_path)))))
    return _dedupe(roots)


def is_within(path: str, root: str) -> bool:
    """True if ``path`` equals ``root`` or is inside it (case-insensitive on Windows)."""
    path_n, root_n = os.path.normcase(path), os.path.normcase(root)
    try:
        return os.path.commonpath([path_n, root_n]) == root_n
    except ValueError:  # different drives on Windows
        return False


def resolve_allowed_path(
    path: str,
    *,
    purpose: str,
    recipe_path: Optional[str] = None,
    base_dir: Optional[str] = None,
) -> str:
    """
    Resolve a recipe-supplied path and ensure it stays inside an allowed root.

    Relative paths are resolved against ``base_dir`` (default: the working
    directory, which is how CPACT has always opened them). Returns the
    resolved real path; raises :class:`PathNotAllowedError` otherwise.
    """
    if not path or not isinstance(path, (str, os.PathLike)):
        raise PathNotAllowedError(f"{purpose}: empty or invalid path {path!r}")
    path = os.fspath(path)
    candidate = path if os.path.isabs(path) else os.path.join(base_dir or os.getcwd(), path)
    real = os.path.realpath(candidate)
    roots = allowed_roots(recipe_path)
    if any(is_within(real, root) for root in roots):
        return real
    raise PathNotAllowedError(
        f"{purpose} '{path}' resolves to '{real}', which is outside the allowed "
        f"locations ({'; '.join(roots)}). Add its folder with --allowed_path "
        f"or the {ENV_ALLOWED_PATHS} environment variable."
    )


_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


def safe_filename(text: object, default: str = "unnamed", max_length: int = 100) -> str:
    """Turn arbitrary text (e.g. a test name) into a single safe file-name component."""
    cleaned = _UNSAFE_FILENAME_CHARS.sub("_", str(text if text is not None else "")).strip("._")
    return (cleaned or default)[:max_length]
