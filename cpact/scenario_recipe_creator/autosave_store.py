"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.


This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

===============================================================================
Qt-free autosave storage for the scenario recipe creator.

Each editor instance writes to its own file (timestamp + PID + random suffix,
so two instances started in the same second never share a file). Writes go
through a temp file + os.replace() so a crash never leaves a truncated
autosave, and only the newest ``keep`` autosaves are retained (the current
instance's file is never pruned).
===============================================================================
"""

from __future__ import annotations

import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, List, Optional

import yaml

AUTOSAVE_GLOB = "autosave_*.yaml"


class AutosaveStore:
    def __init__(self, root: Optional[Path] = None, keep: int = 5) -> None:
        self.root = Path(root) if root else Path(tempfile.gettempdir()) / "cpact_autosaves"
        self.root.mkdir(parents=True, exist_ok=True)
        self.keep = keep
        stamp = time.strftime("%Y%m%d_%H%M%S")
        self.current = self.root / f"autosave_{stamp}_{os.getpid()}_{uuid.uuid4().hex[:6]}.yaml"

    def files(self) -> List[Path]:
        """Autosave files, newest first."""
        found = []
        for path in self.root.glob(AUTOSAVE_GLOB):
            try:
                found.append((path.stat().st_mtime, path))
            except OSError:
                continue  # removed by another instance meanwhile
        return [p for _, p in sorted(found, key=lambda item: item[0], reverse=True)]

    def save(self, data: Any) -> Path:
        """Atomically write ``data`` as YAML to this instance's file, then prune old files."""
        fd, tmp = tempfile.mkstemp(prefix=".autosave_", suffix=".tmp", dir=self.root)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                yaml.safe_dump(data, fh, indent=4)
            os.replace(tmp, self.current)
        except BaseException:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise
        self.prune()
        return self.current

    def prune(self) -> None:
        """Keep the newest ``keep`` autosaves (always keeping this instance's file)."""
        for old in [p for p in self.files() if p != self.current][max(self.keep - 1, 0):]:
            try:
                old.unlink()
            except OSError:
                pass

    @staticmethod
    def load(path: Path) -> Any:
        with open(path, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh)
