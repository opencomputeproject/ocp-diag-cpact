"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

===========================================================================
ArtifactCollector implements the post-execution collateral collection phase of a
scenario run. It consumes the `log_url` and `extended_artifacts` fields of a
v0.9 recipe's `recipe_metadata`, pulls the referenced files off the system the
diagnostic ran on, stages them under the run's log directory, and writes a
manifest describing everything that was collected.

Features:
- Resolves `log_url` and every `extended_artifacts[].url` to concrete files.
- Supports plain files, directories (collected recursively), and glob patterns.
- Works over any ConnectionInterface, so local and SSH targets behave the same.
- Stages artifacts under `<log_dir>/artifacts/<TYPE>/` with traversal-safe paths.
- Emits `<log_dir>/artifacts/manifest.json` with size, SHA-256 and status.
- Never fails the scenario: collection problems are reported, not raised.

Classes:
    ArtifactCollector:
        Collects recipe-declared collaterals for a single scenario run.

Usage:
    ArtifactCollector(scenario, context, test_run).collect()
===========================================================================
"""

import os
import re
import json
import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from cpact.system_connections.base_connection import ConnectionInterface
from cpact.system_connections.connection_factory import ConnectionFactory
from cpact.utils.logger_utils import TestLogger

from ocptv.output import LogSeverity

ARTIFACTS_DIRNAME = "artifacts"
MANIFEST_FILENAME = "manifest.json"
LOG_URL_ARTIFACT_TYPE = "LOG"

_UNRESOLVED_PLACEHOLDER = re.compile(r"\{[^{}]+\}")
_UNSAFE_PATH_CHARS = re.compile(r"[^A-Za-z0-9._-]")


class ArtifactCollector:
    """Collects the collaterals a recipe declares once its steps have run."""

    def __init__(
        self,
        scenario: Dict[str, Any],
        context: Any = None,
        test_run: Any = None,
    ) -> None:
        """
        Args:
            scenario (dict): The executed test scenario (v0.9 shape).
            context (Context): Shared execution context, used for identifiers.
            test_run (tv.TestRun): Optional OCP TV run used for structured logs.
        """
        self.scenario = scenario or {}
        self.context = context
        self.test_run = test_run
        self.logger = TestLogger().get_logger()
        self.metadata = self.scenario.get("recipe_metadata", {}) or {}

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def collect(self) -> Optional[Dict[str, Any]]:
        """
        Collect every declared artifact and write the manifest.

        Returns:
            dict | None: The manifest, or None when the recipe declares nothing
            to collect or collection could not be attempted.
        """
        sources = self._declared_sources()
        if not sources:
            self.logger.debug(
                "No log_url or extended_artifacts declared; skipping collection."
            )
            return None

        manifest: Dict[str, Any] = {
            "test_name": self.scenario.get("test_name"),
            "recipe_id": self.metadata.get("recipe_id"),
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "artifacts": [],
            "skipped": [],
        }

        try:
            connection = self._resolve_connection()
        except Exception as e:
            self.logger.error(f"Artifact collection unavailable: {e}")
            self._run_log(LogSeverity.WARNING,
                          f"Artifact collection unavailable: {e}")
            return None

        if connection is None:
            manifest["skipped"].append(
                {"source": "*", "reason": "no usable connection for collection"}
            )
            self._write_manifest(manifest)
            return manifest

        artifacts_root = os.path.join(
            TestLogger().get_log_dir(), ARTIFACTS_DIRNAME)

        for artifact_type, url in sources:
            unresolved = _UNRESOLVED_PLACEHOLDER.search(url)
            if unresolved:
                reason = (
                    f"unresolved placeholder {unresolved.group(0)}; "
                    "declare it under the recipe's 'paths' block"
                )
                self.logger.warning(f"Skipping artifact '{url}': {reason}")
                manifest["skipped"].append({"source": url, "reason": reason})
                continue

            try:
                entries = self._collect_source(
                    connection, artifacts_root, artifact_type, url
                )
            except Exception as e:
                self.logger.error(f"Failed to collect '{url}': {e}")
                manifest["skipped"].append({"source": url, "reason": str(e)})
                continue

            if not entries:
                manifest["skipped"].append(
                    {"source": url, "reason": "no matching files found"}
                )
                continue

            manifest["artifacts"].extend(entries)

        self._write_manifest(manifest)

        collected = len(manifest["artifacts"])
        skipped = len(manifest["skipped"])
        summary = (
            f"Artifact collection complete: {collected} file(s) collected, "
            f"{skipped} source(s) skipped."
        )
        self.logger.info(summary)
        self._run_log(
            LogSeverity.INFO if collected else LogSeverity.WARNING, summary)
        return manifest

    # ------------------------------------------------------------------ #
    # Source discovery
    # ------------------------------------------------------------------ #
    def _declared_sources(self) -> List[Tuple[str, str]]:
        """Return (artifact_type, url) pairs declared by the recipe metadata."""
        sources: List[Tuple[str, str]] = []

        log_url = self.metadata.get("log_url")
        if isinstance(log_url, str) and log_url.strip():
            sources.append((LOG_URL_ARTIFACT_TYPE, log_url.strip()))

        for artifact in self.metadata.get("extended_artifacts", []) or []:
            if not isinstance(artifact, dict):
                continue
            url = artifact.get("url")
            if isinstance(url, str) and url.strip():
                sources.append(
                    (str(artifact.get("type", "OTHER")), url.strip()))

        return sources

    def _resolve_connection(self) -> Optional[ConnectionInterface]:
        """
        Artifacts live wherever the diagnostic ran, so reuse the connection of
        the last command step; fall back to the local system.
        """
        name, conn_type = "local", "Local"
        for step in reversed(self.scenario.get("test_steps", []) or []):
            if step.get("step_type") == "command_execution" and step.get("connection"):
                name = step.get("connection")
                conn_type = step.get("connection_type", "Local")
                break

        connection = ConnectionFactory.get_instance().get_connection(name, conn_type)
        if connection is None:
            return None

        if not connection.is_connected():
            connection.connect()
        return connection

    # ------------------------------------------------------------------ #
    # Collection
    # ------------------------------------------------------------------ #
    def _collect_source(
        self,
        connection: ConnectionInterface,
        artifacts_root: str,
        artifact_type: str,
        url: str,
    ) -> List[Dict[str, Any]]:
        """Download every file matching `url` and return its manifest entries."""
        source_paths = connection.list_files(url)
        if not source_paths:
            self.logger.warning(f"No files matched artifact source: {url}")
            return []

        base = _glob_free_prefix(url)
        type_dir = os.path.join(
            artifacts_root, _sanitize_component(artifact_type))
        log_dir = TestLogger().get_log_dir()
        entries: List[Dict[str, Any]] = []

        for source_path in source_paths:
            destination = os.path.join(
                type_dir, _safe_relative_path(source_path, base))
            os.makedirs(os.path.dirname(destination), exist_ok=True)

            entry: Dict[str, Any] = {
                "type": artifact_type,
                "source_url": url,
                "source_path": source_path,
                "destination": os.path.relpath(destination, log_dir),
            }

            if not connection.download_file(source_path, destination):
                entry["status"] = "failed"
                entry["error"] = "download failed"
                self.logger.error(f"Failed to retrieve artifact {source_path}")
            else:
                entry["status"] = "collected"
                entry["size_bytes"] = os.path.getsize(destination)
                entry["sha256"] = _sha256(destination)
                self.logger.info(
                    f"Collected artifact {source_path} -> {destination}")

            entries.append(entry)

        return entries

    def _write_manifest(self, manifest: Dict[str, Any]) -> None:
        artifacts_root = os.path.join(
            TestLogger().get_log_dir(), ARTIFACTS_DIRNAME)
        os.makedirs(artifacts_root, exist_ok=True)
        manifest_path = os.path.join(artifacts_root, MANIFEST_FILENAME)
        try:
            with open(manifest_path, "w", encoding="utf-8") as handle:
                json.dump(manifest, handle, indent=2)
            self.logger.info(f"Artifact manifest written to: {manifest_path}")
        except Exception as e:
            self.logger.error(f"Failed to write artifact manifest: {e}")

    def _run_log(self, severity: LogSeverity, message: str) -> None:
        if self.test_run is None:
            return
        try:
            self.test_run.add_log(severity=severity, message=message)
        except Exception:
            pass


# ---------------------------------------------------------------------- #
# Helpers
# ---------------------------------------------------------------------- #
def collect_scenario_artifacts(
    scenario: Dict[str, Any], context: Any = None, test_run: Any = None
) -> Optional[Dict[str, Any]]:
    """Run the collection phase without ever letting it fail the scenario."""
    try:
        return ArtifactCollector(scenario, context, test_run).collect()
    except Exception as e:
        TestLogger().get_logger().error(f"Artifact collection failed: {e}")
        if test_run is not None:
            try:
                test_run.add_log(
                    severity=LogSeverity.WARNING,
                    message=f"Artifact collection failed: {e}",
                )
            except Exception:
                pass
        return None


def _glob_free_prefix(url: str) -> str:
    """Return the longest leading portion of `url` that contains no wildcards."""
    parts = url.replace("\\", "/").split("/")
    kept: List[str] = []
    for part in parts:
        if any(ch in part for ch in "*?["):
            break
        kept.append(part)
    return "/".join(kept) or "/"


def _safe_relative_path(source_path: str, base: str) -> str:
    """
    Build a staging path for `source_path` that can never escape the artifacts
    directory, preserving the tree below `base` where possible.
    """
    normalized = source_path.replace("\\", "/")
    base = base.replace("\\", "/").rstrip("/")

    relative = normalized
    if base and normalized.startswith(base + "/"):
        relative = normalized[len(base) + 1:]
        prefix = os.path.basename(base)
        if prefix:
            relative = f"{prefix}/{relative}"

    components = [
        _sanitize_component(part)
        for part in relative.split("/")
        if part not in ("", ".", "..")
    ]
    # Drive letters and UNC prefixes collapse to empty after sanitising.
    components = [part for part in components if part]
    return os.path.join(*components) if components else "artifact"


def _sanitize_component(component: str) -> str:
    return _UNSAFE_PATH_CHARS.sub("_", component).strip("_")


def _sha256(path: str) -> Optional[str]:
    try:
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except Exception:
        return None
