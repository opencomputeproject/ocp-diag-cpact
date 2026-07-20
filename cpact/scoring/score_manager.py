"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

===========================================================================

Provides the core scoring engine and execution state management for the
CPACT scoring framework.

This module implements the primary scoring infrastructure responsible for
tracking execution events, managing scoring contexts, calculating category
scores, and generating aggregated scoring results. It serves as the
central orchestration layer for all scoring-related operations.

The module contains a thread-safe singleton manager that maintains
execution-specific scoring data and coordinates score calculations across
individual executions and aggregate scoring trees. It also includes a
rule-based profile engine that applies configurable scoring bonuses and
adjustments based on execution characteristics and event patterns.

Key Components:
    - ScoreManager:
        Central scoring coordinator responsible for managing execution
        contexts, collecting events, computing scores, and generating
        scoring results.

    - ProfileEngine:
        Configurable rules engine that applies profile-based scoring
        adjustments and bonus calculations.

Features:
    - Thread-safe scoring operations.
    - Execution context lifecycle management.
    - Event-driven score calculation.
    - Category-based scoring aggregation.
    - Tree-level score aggregation.
    - Configurable scoring profiles and rules.
    - External scoring configuration support.
    - Performance-aware concurrent execution support.

Thread Safety:
    - Singleton initialization uses double-checked locking.
    - Context registry access is protected by re-entrant locking.
    - Individual scoring contexts maintain independent locks.
    - No mutable module-level state is exposed.

Design Goals:
    - Centralize scoring and execution state management.
    - Support concurrent execution environments.
    - Provide extensible scoring capabilities.
    - Decouple scoring rules from scoring infrastructure.
    - Maintain predictable and deterministic score calculations.

This implementation follows PEP 257 documentation guidelines and aligns
with CPACT framework coding standards.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


from cpact.core import context
from cpact.scoring.score_models import (
    DEFAULT_CONFIG,
    CategoryScore,
    Event,
    EventType,
    ScoreContext,
    ScoreResult,
    ScoringConfig,
    deep_merge,
)

#: Location of the bundled default configuration file.
_DEFAULT_CONFIG_PATH = Path(__file__).with_name("scoring.json")


# ===========================================================================
# ScoreManager
# ===========================================================================
class ScoreManager:
    """
    Thread-safe singleton responsible for managing scoring operations.

    This class acts as the central coordinator for the scoring framework,
    maintaining execution contexts, processing scoring events, applying
    scoring rules, and generating aggregated score results.

    The manager owns all runtime scoring state and provides APIs for
    execution lifecycle management, event collection, score calculation,
    and result retrieval.

    Responsibilities:
        - Manage execution scoring contexts.
        - Register and process scoring events.
        - Calculate category and aggregate scores.
        - Maintain execution lifecycle state.
        - Load and apply scoring configuration.
        - Support concurrent scoring operations.
        - Coordinate profile-based scoring adjustments.

    Attributes:
        _instance:
            Singleton instance of the scoring manager.

        _contexts:
            Registry of active scoring contexts.

        _config:
            Active scoring configuration.

        _lock:
            Synchronization lock protecting shared resources.

    Notes:
        Each execution context maintains its own synchronization
        mechanism to minimize contention during concurrent execution.
    """

    _instance: Optional["ScoreManager"] = None
    _singleton_lock: threading.Lock = threading.Lock()

    # -- construction -------------------------------------------------------
    def __new__(cls, *args: Any, **kwargs: Any) -> "ScoreManager":
        """Return the one and only instance, creating it on first call."""
        if cls._instance is None:
            with cls._singleton_lock:
                # Double-checked locking: re-test inside the lock.
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._initialized = False
                    cls._instance = instance
        return cls._instance

    def __init__(self, config_path: Optional[Path | str] = None) -> None:
        """Initialise singleton state exactly once.

        Parameters
        ----------
        config_path:
            Optional path to a user configuration file. Supplied only on the
            first construction; ignored on subsequent calls (use
            :meth:`load_config` to change configuration later).
        """
        # ``__init__`` runs on every ``ScoreManager()`` call; guard so we only
        # build state once.
        if getattr(self, "_initialized", False):
            return
        self._contexts: Dict[str, ScoreContext] = {}
        self._contexts_lock: threading.RLock = threading.RLock()
        self._config: ScoringConfig = self.load_config(config_path)
        self._initialized = True

    # -- singleton management ----------------------------------------------
    @classmethod
    def instance(cls, config_path: Optional[Path | str] = None) -> "ScoreManager":
        """Return the singleton, constructing it if necessary."""
        return cls(config_path)

    @classmethod
    def reset_instance(cls) -> None:
        """Discard the singleton. Intended for unit-test isolation only."""
        with cls._singleton_lock:
            cls._instance = None

    # -- configuration ------------------------------------------------------
    def load_config(self, config_path: Optional[Path | str] = None) -> ScoringConfig:
        """Load and merge configuration, returning a :class:`ScoringConfig`.

        Resolution order:

        1. Start from :data:`~scoring.models.DEFAULT_CONFIG`.
        2. If ``config_path`` is ``None``, fall back to the bundled
           ``scoring.json`` (if present).
        3. Deep-merge the user file on top of the defaults so partial configs
           preserve unspecified keys.

        Raises
        ------
        ValueError
            If the file exists but contains invalid JSON or values.
        """
        merged: Dict[str, Any] = dict(DEFAULT_CONFIG)
        path = Path(config_path) if config_path else _DEFAULT_CONFIG_PATH
        if path.exists():
            try:
                user_cfg = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Could not parse config {path}: {exc}") from exc
            if not isinstance(user_cfg, dict):
                raise ValueError(f"Config root must be an object: {path}")
            merged = deep_merge(merged, user_cfg)
        config = ScoringConfig.from_dict(merged)
        # Persist when called post-init so callers can reconfigure at runtime.
        if getattr(self, "_initialized", False):
            self._config = config
        return config

    @property
    def config(self) -> ScoringConfig:
        """The active, merged scoring configuration."""
        return self._config

    # -- lifecycle ----------------------------------------------------------
    def start_run(
        self,
        execution_id: str,
        recipe_name: str,
        parent_execution_id: Optional[str] = None,
    ) -> ScoreContext:
        """
        Start a recipe execution.

        If the execution is already active, return the existing context.
        If the execution has already completed, raise an error (or reset,
        depending on framework policy).
        """

        if not execution_id:
            raise ValueError("execution_id must be a non-empty string")

        with self._contexts_lock:

            existing = self._contexts.get(execution_id)

            if existing is not None:

                with existing.lock:
                    if existing.end_time is None:
                        return existing
                    raise ValueError(
                        f"Execution '{execution_id}' has already completed."
                    )
            context = ScoreContext(
                execution_id=execution_id,
                recipe_name=recipe_name,
                parent_execution_id=parent_execution_id,
                start_time=time.time(),
            )

            self._contexts[execution_id] = context

            if parent_execution_id is not None:
                self._link_child(
                    parent_execution_id,
                    execution_id,
                )

            return context

    def start_nested_run(
        self,
        parent_execution_id: str,
        execution_id: str,
        recipe_name: str,
    ) -> ScoreContext:
        """Start a child run under ``parent_execution_id``.

        Convenience wrapper around :meth:`start_run` that makes the parent
        relationship explicit and also records a ``NESTED_RECIPE`` event on the
        parent for traceability.
        """
        context = self.start_run(
            execution_id, recipe_name, parent_execution_id=parent_execution_id
        )
        self.emit_event(
            parent_execution_id,
            EventType.NESTED_RECIPE,
            passed=True,
            metadata={"child_execution_id": execution_id, "recipe_name": recipe_name},
        )
        return context

    def _link_child(self, parent_execution_id: str, child_execution_id: str) -> None:
        """Record ``child_execution_id`` under its parent (internal)."""
        parent = self._require(parent_execution_id)
        with parent.lock:
            if child_execution_id not in parent.child_execution_ids:
                parent.child_execution_ids.append(child_execution_id)

    def end_run(self, execution_id: str) -> ScoreContext:
        """Mark an execution finished by stamping its end time."""
        context = self._require(execution_id)
        with context.lock:
            context.end_time = time.time()
        return context

    def reset_run(self, execution_id: str) -> ScoreContext:
        """Clear an execution's accumulated scores (keeps it registered)."""
        context = self._require(execution_id)
        context.reset()
        return context

    def delete_run(self, execution_id: str, *, recursive: bool = False) -> None:
        """Remove an execution from the registry.

        Parameters
        ----------
        execution_id:
            The execution to delete.
        recursive:
            When ``True``, delete the whole subtree. When ``False`` (default),
            delete only this node and detach it from its parent's child list;
            any children are left orphaned but intact.

        Raises
        ------
        KeyError
            If ``execution_id`` is unknown.
        """
        with self._contexts_lock:
            context = self._require(execution_id)
            if recursive:
                for child_id in list(context.child_execution_ids):
                    if child_id in self._contexts:
                        self.delete_run(child_id, recursive=True)
            # Detach from parent.
            parent_id = context.parent_execution_id
            if parent_id and parent_id in self._contexts:
                parent = self._contexts[parent_id]
                with parent.lock:
                    if execution_id in parent.child_execution_ids:
                        parent.child_execution_ids.remove(execution_id)
            del self._contexts[execution_id]

    # -- registry access ----------------------------------------------------
    def get_context(self, execution_id: str) -> Optional[ScoreContext]:
        """Return the context for ``execution_id`` or ``None`` if absent."""
        with self._contexts_lock:
            return self._contexts.get(execution_id)

    def _require(self, execution_id: str) -> ScoreContext:
        """Return the context or raise :class:`KeyError` (internal)."""
        with self._contexts_lock:
            context = self._contexts.get(execution_id)
        if context is None:
            raise KeyError(f"Unknown execution_id: {execution_id!r}")
        return context

    def all_execution_ids(self) -> List[str]:
        """Return a snapshot list of every registered execution id."""
        with self._contexts_lock:
            return list(self._contexts.keys())

    def get_all_results(self) -> List[ScoreResult]:
        """
        Return the calculated score for every execution context.
        """
        with self._contexts_lock:
            execution_ids = list(self._contexts.keys())

        return [self.calculate(execution_id) for execution_id in execution_ids]

    def get_root_results(self) -> List[ScoreResult]:
        """
        Return only root recipe results.
        Nested recipes are excluded.
        """
        with self._contexts_lock:
            roots = [
                ctx.execution_id
                for ctx in self._contexts.values()
                if ctx.parent_execution_id is None
            ]

        return [self.calculate(eid) for eid in roots]

    def root_execution_ids(self) -> List[str]:
        """Return execution ids that have no parent (tree roots)."""
        with self._contexts_lock:
            return [
                eid
                for eid, ctx in self._contexts.items()
                if ctx.parent_execution_id is None
            ]

    # -- event API ----------------------------------------------------------
    def emit_event(
        self,
        execution_id: str,
        event_type: EventType,
        passed: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Event:
        """Record an event and fold it into the target context.

        This is the single generic entry point; the convenience methods below
        are thin wrappers. Counter updates are derived from ``event_type`` so
        no category-specific API is hardcoded into callers.

        Raises
        ------
        KeyError
            If ``execution_id`` is unknown.
        TypeError
            If ``event_type`` is not an :class:`EventType`.
        """
        if not isinstance(event_type, EventType):
            raise TypeError("event_type must be an EventType member")
        context = self._require(execution_id)
        event = Event(event_type=event_type, passed=passed, metadata=metadata or {})
        with context.lock:
            context.events.append(event)
            self._apply_event(context, event)
        return event

    @staticmethod
    def _apply_event(context: ScoreContext, event: Event) -> None:
        """Update context counters based on an event (caller holds the lock)."""
        etype = event.event_type
        if etype is EventType.SCHEMA_VALIDATION:
            context.schema_exists = True
            context.schema_passed = event.passed
        elif etype is EventType.MAP_VALIDATION:
            context.map_exists = True
            context.map_passed = event.passed
        elif etype is EventType.EXECUTION_STEP:
            context.total_steps += 1
            if event.passed:
                context.passed_steps += 1
            else:
                context.failed_steps += 1
        elif etype is EventType.PROFILE_SCORE:
            context.profile_score += float(event.metadata.get("score", 0.0))
        elif etype is EventType.NESTED_RECIPE:
            child_id = event.metadata.get("child_execution_id")
            if child_id and child_id not in context.child_execution_ids:
                context.child_execution_ids.append(child_id)

    # -- convenience wrappers ----------------------------------------------
    def schema_validation(
        self,
        execution_id: str,
        passed: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Event:
        """Record the schema validation outcome for an execution."""
        return self.emit_event(
            execution_id, EventType.SCHEMA_VALIDATION, passed, metadata
        )

    def map_validation(
        self,
        execution_id: str,
        passed: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Event:
        """Record the (optional) map validation outcome for an execution."""
        return self.emit_event(execution_id, EventType.MAP_VALIDATION, passed, metadata)

    def execution_step(
        self,
        execution_id: str,
        passed: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Event:
        """Record a single execution step result."""
        metadata.update(
            {
                "score": 0 if not passed else self.config.execution_weight,
                "max_score": self.config.execution_weight,
            }
        )
        return self.emit_event(execution_id, EventType.EXECUTION_STEP, passed, metadata)

    def record_execution_step(self, execution_id, execution_result):
        self.execution_step(
            execution_id=execution_id, passed=execution_result.passed, meta_data={}
        )

    def add_profile_score(
        self,
        execution_id: str,
        score: float,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Event:
        """Add profile-engine bonus points to an execution.

        The points are accumulated on :attr:`ScoreContext.profile_score`; the
        profile engine uses this to feed results back without ever touching the
        manager's internals.
        """
        meta = dict(metadata or {})
        meta["score"] = float(score)
        return self.emit_event(execution_id, EventType.PROFILE_SCORE, True, meta)

    def record_schema_validation(
        self,
        execution_id,
        validation_result,
    ):

        # ---------------- Schema ---------------- #
        self.schema_validation(
            execution_id,
            validation_result.recipe_schema_valid,
            metadata={
                "file": getattr(validation_result, "recipe_schema", "Recipe Schema"),
                "validator": "RecipeSchemaValidator",
                "score": (
                    self.config.schema_weight
                    if validation_result.recipe_schema_valid
                    else 0
                ),
                "max_score": self.config.schema_weight,
                "message": (
                    "Schema validation passed"
                    if validation_result.recipe_schema_valid
                    else "Schema validation failed"
                ),
            },
        )

        # ---------------- Map ---------------- #

        self.map_validation(
            execution_id,
            validation_result.map_schema_valid,
            metadata={
                "file": getattr(validation_result, "map_schema", "Recipe Map"),
                "validator": "MapSchemaValidator",
                "score": (
                    self.config.map_weight if validation_result.map_schema_valid else 0
                ),
                "max_score": self.config.map_weight,
                "message": (
                    "Map validation passed"
                    if validation_result.map_schema_valid
                    else "Map validation failed"
                ),
            },
        )

    # -- scoring ------------------------------------------------------------
    def calculate(self, execution_id: str) -> ScoreResult:
        """Compute the *local* normalised score for a single execution.

        Only categories that are *present* contribute to the available total,
        so a recipe with no map file is normalised against schema + execution
        and is never penalised for the absence.

        Returns
        -------
        ScoreResult
            The category breakdown and normalised final score (0..100).
        """
        context = self._require(execution_id)
        cfg = self._config
        with context.lock:
            categories: List[CategoryScore] = []

            # Schema category (present iff a schema validation event arrived).
            schema_earned = cfg.schema_weight if context.schema_passed else 0.0
            categories.append(
                CategoryScore(
                    name="Schema",
                    earned=schema_earned if context.schema_exists else 0.0,
                    maximum=cfg.schema_weight,
                    status=(
                        ("PASS" if context.schema_passed else "FAIL")
                        if context.schema_exists
                        else "N/A"
                    ),
                    present=context.schema_exists,
                )
            )
            # Map category (optional).
            map_earned = cfg.map_weight if context.map_passed else 0.0
            categories.append(
                CategoryScore(
                    name="Map",
                    earned=map_earned if context.map_exists else 0.0,
                    maximum=cfg.map_weight,
                    status=(
                        ("PASS" if context.map_passed else "FAIL")
                        if context.map_exists
                        else "N/A"
                    ),
                    present=context.map_exists,
                )
            )

            # Execution category (present iff at least one step ran).
            exec_present = True
            if context.total_steps == 0:

                exec_earned = 0.0
                exec_status = "NOT EXECUTED"

            else:

                exec_earned = (
                    context.passed_steps / context.total_steps
                ) * cfg.execution_weight

                if context.failed_steps > 0:
                    exec_status = (
                        f"{context.passed_steps}/{context.total_steps} "
                        f"(Failed: {context.failed_steps})"
                    )
                else:
                    exec_status = f"{context.passed_steps}/{context.total_steps}"

            categories.append(
                CategoryScore(
                    name="Execution",
                    earned=exec_earned,
                    maximum=cfg.execution_weight,
                    status=exec_status,
                    present=True,  # Always present
                )
            )

            earned = sum(c.earned for c in categories if c.present)

            available = cfg.schema_weight + cfg.execution_weight
            if context.map_exists:
                available += cfg.map_weight

            # for c in categories:
            #     print(f"Category: {c.name}, Earned: {c.earned}, Maximum: {c.maximum}, Status: {c.status}, Present: {c.present}")
            # available = sum(c.maximum for c in categories if c.present)
            # print("Available score is ", available)
            # final = (earned / available * 100.0) if available > 0 else 0.0
            # print("Final Score is ", final)
            final = (earned / available) * 100.0 if available > 0 else 0.0
            return ScoreResult(
                execution_id=context.execution_id,
                recipe_name=context.recipe_name,
                categories=categories,
                earned_score=earned,
                available_score=available,
                final_score=round(final, 2),
                profile_score=context.profile_score,
                total_steps=context.total_steps,
                passed_steps=context.passed_steps,
            )

    def calculate_tree_score(self, execution_id: str) -> float:
        """Compute the aggregate score for an execution and all descendants.

        The aggregate is a weighted average of every node's local score,
        weighted by that node's step count, so deep/large child recipes
        influence the result proportionally rather than equally.

        When the entire subtree has zero steps (nothing to weight by), the
        method falls back to a simple mean of the local scores.
        """
        nodes = self._collect_subtree(execution_id)

        weighted_sum = 0.0
        total_weight = 0
        local_scores: List[float] = []
        for ctx in nodes:
            local = self.calculate(ctx.execution_id).final_score
            local_scores.append(local)
            weight = ctx.total_steps
            weighted_sum += local * weight
            total_weight += weight

        if total_weight > 0:
            return weighted_sum / total_weight
        if local_scores:
            return sum(local_scores) / len(local_scores)
        return 0.0

    def _collect_subtree(self, execution_id: str) -> List[ScoreContext]:
        """Return all contexts in the subtree rooted at ``execution_id``.

        Cycle-safe via a visited set (the topology is a tree in normal use, but
        defensive traversal guards against accidental loops).
        """
        ordered: List[ScoreContext] = []
        visited: set[str] = set()

        def _walk(eid: str) -> None:
            if eid in visited:
                return
            visited.add(eid)
            ctx = self.get_context(eid)
            if ctx is None:
                return
            ordered.append(ctx)
            with ctx.lock:
                children = list(ctx.child_execution_ids)
            for child in children:
                _walk(child)

        _walk(execution_id)
        return ordered


# ===========================================================================
# ProfileEngine
# ===========================================================================
class ProfileEngine:
    """Apply declarative profile rules to an execution's event stream.

    The engine awards bonus points based on rules, typically loaded from JSON.
    It is deliberately decoupled from :class:`ScoreManager`: it *reads* a
    context's event stream and *writes* results back via
    :meth:`ScoreManager.add_profile_score`, so new scoring dimensions can be
    added without modifying the manager.

    Rule shape::

        {"step_type": "log_analysis", "contains": "diagnostic_analysis", "score": 5}

    A rule matches an ``EXECUTION_STEP`` event when the event metadata's
    ``step_type`` equals ``rule['step_type']`` and the ``rule['contains']``
    substring appears in the configured match field (or, as a fallback, anywhere
    in the metadata payload).
    """

    def __init__(
        self,
        rules: Optional[List[Dict[str, Any]]] = None,
        config_path: Optional[Path | str] = None,
        match_field: str = "detail",
    ) -> None:
        """Create the engine.

        Parameters
        ----------
        rules:
            Explicit list of rule dictionaries. Takes precedence over
            ``config_path``.
        config_path:
            Path to a JSON file with a top-level ``"profile_rules"`` array.
        match_field:
            The metadata key whose value the ``contains`` test is applied to. If
            the key is absent on an event, the test falls back to the string
            form of the entire metadata dict.
        """
        if rules is not None:
            self.rules: List[Dict[str, Any]] = list(rules)
        elif config_path is not None:
            self.rules = self._load_rules(Path(config_path))
        else:
            self.rules = []
        self.match_field = match_field

    @staticmethod
    def _load_rules(path: Path) -> List[Dict[str, Any]]:
        """Load the ``profile_rules`` array from a JSON config file."""
        if not path.exists():
            raise FileNotFoundError(f"Profile config not found: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        rules = data.get("profile_rules", [])
        if not isinstance(rules, list):
            raise ValueError("'profile_rules' must be a list")
        return rules

    def _rule_matches(self, rule: Dict[str, Any], metadata: Dict[str, Any]) -> bool:
        """Return ``True`` if ``rule`` matches an event's ``metadata``."""
        if rule.get("step_type") != metadata.get("step_type"):
            return False
        needle = rule.get("contains")
        if needle is None:
            return True
        haystack = metadata.get(self.match_field)
        haystack_str = str(haystack) if haystack is not None else str(metadata)
        return str(needle) in haystack_str

    def evaluate(
        self, execution_id: str, manager: Optional[ScoreManager] = None
    ) -> float:
        """Score one execution against the rules and feed the result back.

        Parameters
        ----------
        execution_id:
            The execution to evaluate.
        manager:
            The manager to read from / write to. Defaults to the singleton.

        Returns
        -------
        float
            The total bonus points awarded (also recorded on the context via
            :meth:`ScoreManager.add_profile_score`).
        """
        manager = manager or ScoreManager()
        context = manager.get_context(execution_id)
        if context is None:
            raise KeyError(f"Unknown execution_id: {execution_id!r}")

        total = 0.0
        with context.lock:
            step_events = [
                e for e in context.events if e.event_type is EventType.EXECUTION_STEP
            ]
        for event in step_events:
            for rule in self.rules:
                if self._rule_matches(rule, event.metadata):
                    total += float(rule.get("score", 0.0))

        if total:
            manager.add_profile_score(
                execution_id, total, metadata={"source": "profile_engine"}
            )
        return total
