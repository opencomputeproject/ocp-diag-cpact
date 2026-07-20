"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

===========================================================================

Provides the foundational data models and configuration structures for the
CPACT scoring framework.

This module defines the core domain objects used throughout the scoring
subsystem, including event definitions, scoring configuration models,
execution context state, score result objects, and supporting utility
functions. It serves as the shared data layer between scoring engines,
rule processors, and reporting components.

The module is intentionally kept free from business logic to ensure
maintainability, reusability, and testability. Scoring calculations,
rule evaluation, and aggregation logic are implemented by higher-level
engine components that consume the models defined here.

Components
----------
Events
    Defines scoring event types and immutable event records used to
    capture execution activity.

Configuration
    Provides default scoring configuration, configuration merge
    utilities, and immutable configuration models.

Score Results
    Defines score-related value objects representing category scores
    and execution scoring outcomes.

Execution Context
    Provides mutable execution state used during score calculation
    and event processing.

Classes
-------
EventType
    Enumeration of supported scoring event categories.

Event
    Immutable record representing a scoring event.

ScoringConfig
    Immutable scoring configuration model.

CategoryScore
    Represents the score achieved within a specific category.

ScoreResult
    Represents the computed scoring outcome for an execution.

ScoreContext
    Maintains runtime scoring state for a single execution.

StepResult
    Represents the outcome of an individual execution step.

Functions
---------
deep_merge
    Recursively merges user-provided configuration values with
    framework defaults.

Design Goals
------------
- Establish a stable scoring domain model.
- Provide strongly typed configuration and scoring structures.
- Separate data representation from business logic.
- Support thread-safe scoring operations.
- Enable future scoring framework extensibility.

This implementation follows PEP 257 documentation conventions and
aligns with CPACT framework coding standards.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class EventType(Enum):
    """Semantic categories of events emitted during a recipe execution.

    Members
    -------
    SCHEMA_VALIDATION
        The recipe's schema was validated (``passed`` reflects the outcome).
    MAP_VALIDATION
        The recipe's optional map file was validated.
    EXECUTION_STEP
        A single execution step finished (``passed`` reflects success).
    PROFILE_SCORE
        A profile-engine rule awarded points (carried in ``metadata['score']``).
    NESTED_RECIPE
        A child recipe was attached to this execution.
    """

    SCHEMA_VALIDATION = "schema_validation"
    MAP_VALIDATION = "map_validation"
    EXECUTION_STEP = "execution_step"
    PROFILE_SCORE = "profile_score"
    NESTED_RECIPE = "nested_recipe"

    def __str__(self) -> str:  # pragma: no cover - cosmetic only
        return self.value


@dataclass(frozen=True)
class Event:
    """An immutable record of something that happened during an execution.

    Attributes
    ----------
    event_type:
        The :class:`EventType` describing what happened.
    passed:
        Whether the event represents a successful outcome. Meaningless for
        purely informational events (e.g. ``PROFILE_SCORE``) but kept uniform
        so the event stream is easy to filter.
    metadata:
        Arbitrary, JSON-serialisable contextual data. The framework never
        requires specific keys, which keeps the API generic; convenience
        helpers and the profile engine populate well-known keys by convention.
    timestamp:
        Unix epoch seconds captured at construction time.
    """

    event_type: EventType
    passed: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serialisable representation of the event."""
        return {
            "event_type": self.event_type.value,
            "passed": self.passed,
            "metadata": dict(self.metadata),
            "timestamp": self.timestamp,
        }


# ===========================================================================
# Configuration
# ===========================================================================
#: Built-in default weights, used when no configuration file is supplied or to
#: back-fill keys missing from a partial user configuration.
DEFAULT_CONFIG: Dict[str, Any] = {
    "weights": {
        "schema": 30,
        "map": 20,
        "execution": 50,
    },
    "profile_rules": [],
}


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge ``override`` onto ``base`` without mutating inputs.

    Nested dictionaries are merged key-by-key so that a partial user config
    (e.g. only ``{"weights": {"execution": 70}}``) preserves every default it
    does not explicitly set. Non-dict values in ``override`` win outright.

    Parameters
    ----------
    base:
        The baseline mapping (typically :data:`DEFAULT_CONFIG`).
    override:
        The mapping whose values take precedence.

    Returns
    -------
    dict
        A new merged dictionary.
    """
    result: Dict[str, Any] = dict(base)
    for key, value in override.items():
        existing = result.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            result[key] = deep_merge(existing, value)
        else:
            result[key] = value
    return result


@dataclass(frozen=True)
class ScoringConfig:
    """Immutable, validated view of the merged scoring configuration.

    Attributes
    ----------
    schema_weight, map_weight, execution_weight:
        Category weights. They need not sum to 100 because the final score is
        normalised against whichever categories are actually present.
    profile_rules:
        Raw rule dictionaries consumed by
        :class:`~scoring.engine.ProfileEngine`.
    """

    schema_weight: float = 30.0
    map_weight: float = 20.0
    execution_weight: float = 50.0
    profile_rules: List[Dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "ScoringConfig":
        """Build a :class:`ScoringConfig` from an already-merged mapping."""
        weights = raw.get("weights", {})
        try:
            return cls(
                schema_weight=float(weights.get("schema", 30)),
                map_weight=float(weights.get("map", 20)),
                execution_weight=float(weights.get("execution", 50)),
                profile_rules=list(raw.get("profile_rules", [])),
            )
        except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
            raise ValueError(f"Invalid scoring configuration: {exc}") from exc


# ===========================================================================
# Score value objects
# ===========================================================================
@dataclass(frozen=True)
class CategoryScore:
    """Score earned within a single scoring category.

    Attributes
    ----------
    name:
        Human-readable category label (``"Schema"``, ``"Map"``, ``"Execution"``).
    earned:
        Points earned (already weighted).
    maximum:
        Maximum points available for the category (its weight).
    status:
        Short status string for display, e.g. ``"PASS"``, ``"FAIL"`` or
        ``"9/10"`` for execution.
    present:
        Whether the category applies to this recipe. Absent categories
        contribute nothing to either the earned or available totals so the
        recipe is not penalised for, e.g., having no map file.
    """

    name: str
    earned: float
    maximum: float
    status: str
    present: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serialisable representation."""
        return {
            "name": self.name,
            "earned": round(self.earned, 4),
            "maximum": round(self.maximum, 4),
            "status": self.status,
            "present": self.present,
        }


@dataclass(frozen=True)
class ScoreResult:
    """The computed score for a single recipe execution (local, not aggregate).

    Attributes
    ----------
    execution_id, recipe_name:
        Identity of the scored execution.
    categories:
        Per-category breakdown (including absent categories, flagged via
        :attr:`CategoryScore.present`).
    earned_score, available_score:
        Raw earned points and the points that were actually in play.
    final_score:
        ``earned_score / available_score * 100`` (0.0 when nothing is in play).
    profile_score:
        Profile-engine bonus points recorded on the context (reported
        separately; not folded into :attr:`final_score`).
    total_steps, passed_steps:
        Execution step counters, surfaced for reporting.
    """

    execution_id: str
    recipe_name: str
    categories: List[CategoryScore]
    earned_score: float
    available_score: float
    final_score: float
    profile_score: float = 0.0
    total_steps: int = 0
    passed_steps: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serialisable representation."""
        return {
            "execution_id": self.execution_id,
            "recipe_name": self.recipe_name,
            "categories": [c.to_dict() for c in self.categories],
            "earned_score": round(self.earned_score, 4),
            "available_score": round(self.available_score, 4),
            "final_score": round(self.final_score, 4),
            "profile_score": round(self.profile_score, 4),
            "total_steps": self.total_steps,
            "passed_steps": self.passed_steps,
        }


# ===========================================================================
# Mutable per-execution context
# ===========================================================================
@dataclass
class ScoreContext:
    """Mutable state for one recipe execution.

    Instances are created and owned by the :class:`~scoring.engine.ScoreManager`.
    Each context carries its own re-entrant lock so concurrent events targeting
    *different* executions never contend, while events targeting the *same*
    execution are serialised for consistency.
    """

    execution_id: str
    recipe_name: str

    parent_execution_id: Optional[str] = None
    child_execution_ids: List[str] = field(default_factory=list)

    schema_exists: bool = False
    schema_passed: bool = False

    map_exists: bool = False
    map_passed: bool = False

    # step_results: List[StepResult] = []
    total_steps: int = 0
    passed_steps: int = 0
    failed_steps: int = 0

    events: List[Event] = field(default_factory=list)

    profile_score: float = 0.0

    start_time: Optional[float] = None
    end_time: Optional[float] = None

    # Per-context re-entrant lock. Excluded from repr/eq/hash so that contexts
    # remain comparable and printable.
    lock: threading.RLock = field(
        default_factory=threading.RLock, repr=False, compare=False
    )

    def reset(self) -> None:
        """Clear all accumulated scoring state while preserving identity.

        Identity fields (``execution_id``, ``recipe_name``,
        ``parent_execution_id``) and the parent/child topology are retained so a
        run can be re-executed in place; only scoring data is wiped.
        """
        with self.lock:
            self.schema_exists = False
            self.schema_passed = False
            self.map_exists = False
            self.map_passed = False
            self.total_steps = 0
            self.passed_steps = 0
            self.events = []
            self.profile_score = 0.0
            self.start_time = None
            self.end_time = None

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serialisable snapshot of the raw context state."""
        with self.lock:
            return {
                "execution_id": self.execution_id,
                "recipe_name": self.recipe_name,
                "parent_execution_id": self.parent_execution_id,
                "child_execution_ids": list(self.child_execution_ids),
                "schema_exists": self.schema_exists,
                "schema_passed": self.schema_passed,
                "map_exists": self.map_exists,
                "map_passed": self.map_passed,
                "total_steps": self.total_steps,
                "passed_steps": self.passed_steps,
                "profile_score": self.profile_score,
                "start_time": self.start_time,
                "end_time": self.end_time,
                "events": [e.to_dict() for e in self.events],
            }


@dataclass
class StepResult:

    step_no: int

    step_name: str

    step_type: str

    status: str

    score: float = 0

    max_score: float = 0

    execution_time: float = 0

    message: str = ""

    output: str = ""

    metadata: Dict[str, Any] = field(default_factory=dict)
