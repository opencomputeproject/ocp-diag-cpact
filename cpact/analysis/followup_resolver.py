"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

===========================================================================
FollowUpResolver inspects the OCPTV output produced by a diagnostic recipe and
determines whether the run asked for another recipe to be executed.

A DiagnosticIssue is actionable as a follow-up when either:
- it carries an explicit `follow_up_recipe_id`, or
- its `action` is `FOLLOWUP_RECIPE`, in which case the recipe id is looked up in
  the scenario's DRC map under the issue's `drc`.

The second form is the one the current schemas support: the DiagnosticIssue
extension schema sets `additionalProperties: false` and has no recipe field, so
the binding from DRC to follow-up recipe lives in the DRC map.

Classes:
    FollowUpResolver:
        Extracts ordered, de-duplicated follow-up recipe ids for one run.

Usage:
    FollowUpResolver(scenario, manifest).resolve()
===========================================================================
"""

import os
import json
from typing import Any, Dict, Iterable, List, Optional, Set

from cpact.utils.logger_utils import TestLogger

DIAGNOSTIC_ISSUE_NAME = "DiagnosticIssue"
FOLLOWUP_ACTION = "FOLLOWUP_RECIPE"
OCPTV_SUFFIXES = (".json", ".jsonl")


class FollowUpResolver:
    """Derives the follow-up recipe ids requested by a completed recipe run."""

    def __init__(
        self,
        scenario: Dict[str, Any],
        manifest: Optional[Dict[str, Any]] = None,
        log_dir: Optional[str] = None,
    ) -> None:
        """
        Args:
            scenario (dict): The executed scenario, used for its `map_file`.
            manifest (dict): Artifact manifest from the collection phase; its
                entries point at the OCPTV files staged for this run.
            log_dir (str): Run log directory the manifest destinations are
                relative to. Defaults to the active TestLogger directory.
        """
        self.scenario = scenario or {}
        self.manifest = manifest or {}
        self.log_dir = log_dir or TestLogger().get_log_dir()
        self.logger = TestLogger().get_logger()

    def resolve(self) -> List[str]:
        """
        Returns:
            List[str]: Follow-up recipe ids in first-seen order, de-duplicated.
        """
        ocptv_files = self._ocptv_files()
        if not ocptv_files:
            self.logger.debug(
                "No OCPTV artifacts collected; no follow-up recipes to resolve."
            )
            return []

        drc_map = self._load_drc_map()
        recipe_ids: List[str] = []
        seen: Set[str] = set()

        for path in ocptv_files:
            for issue in self._diagnostic_issues(path):
                recipe_id = self._follow_up_for(issue, drc_map)
                if not recipe_id or recipe_id in seen:
                    continue
                seen.add(recipe_id)
                recipe_ids.append(recipe_id)
                self.logger.info(
                    f"DRC {issue.get('drc')} (issue {issue.get('issueId')}) "
                    f"requests follow-up recipe: {recipe_id}"
                )

        return recipe_ids

    # ------------------------------------------------------------------ #
    # OCPTV discovery and parsing
    # ------------------------------------------------------------------ #
    def _ocptv_files(self) -> List[str]:
        """Absolute paths of the OCPTV artifacts staged for this run."""
        files: List[str] = []
        for entry in self.manifest.get("artifacts", []) or []:
            if entry.get("status") != "collected":
                continue
            destination = entry.get("destination")
            if not destination or not destination.lower().endswith(OCPTV_SUFFIXES):
                continue
            path = os.path.join(self.log_dir, destination)
            if os.path.isfile(path):
                files.append(path)
        return files

    def _diagnostic_issues(self, path: str) -> Iterable[Dict[str, Any]]:
        """Yield DiagnosticIssue payloads from an OCPTV JSON or JSONL file."""
        try:
            with open(path, "r", encoding="utf-8") as handle:
                content = handle.read()
        except Exception as e:
            self.logger.warning(f"Cannot read OCPTV artifact {path}: {e}")
            return []

        issues: List[Dict[str, Any]] = []
        for record in _iter_json_records(content):
            extension = (record.get("testStepArtifact")
                         or {}).get("extension") or {}
            payload = extension.get("content") or {}
            if not isinstance(payload, dict):
                continue
            if (
                extension.get("name") == DIAGNOSTIC_ISSUE_NAME
                or payload.get("@type") == DIAGNOSTIC_ISSUE_NAME
            ):
                issues.append(payload)
        return issues

    # ------------------------------------------------------------------ #
    # Follow-up resolution
    # ------------------------------------------------------------------ #
    def _follow_up_for(
        self, issue: Dict[str, Any], drc_map: Dict[str, Any]
    ) -> Optional[str]:
        explicit = issue.get("follow_up_recipe_id")
        if isinstance(explicit, str) and explicit.strip():
            return explicit.strip()

        if issue.get("action") != FOLLOWUP_ACTION:
            return None

        drc = issue.get("drc")
        if not drc:
            self.logger.warning(
                f"Issue {issue.get('issueId')} requests {FOLLOWUP_ACTION} but has no DRC."
            )
            return None

        entry = drc_map.get(drc) or {}
        mapped = entry.get("follow_up_recipe_id")
        if isinstance(mapped, str) and mapped.strip():
            return mapped.strip()

        self.logger.warning(
            f"DRC {drc} requests {FOLLOWUP_ACTION} but the DRC map defines no "
            "follow_up_recipe_id for it."
        )
        return None

    def _load_drc_map(self) -> Dict[str, Any]:
        map_file = self.scenario.get("map_file")
        if not map_file:
            return {}
        try:
            with open(map_file, "r", encoding="utf-8") as handle:
                return json.load(handle).get("DRCs", {}) or {}
        except Exception as e:
            self.logger.warning(f"Cannot load DRC map {map_file}: {e}")
            return {}


def _iter_json_records(content: str) -> Iterable[Dict[str, Any]]:
    """
    Yield records from OCPTV output, which may be JSONL or a single JSON
    document containing an array of artifacts.
    """
    stripped = content.lstrip()
    if stripped.startswith("["):
        try:
            for record in json.loads(stripped):
                if isinstance(record, dict):
                    yield record
            return
        except json.JSONDecodeError:
            pass

    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            yield record
