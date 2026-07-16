"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

===================================================================

validation_result.py

Provides standardized result models for schema validation operations within
the CPACT schema validation framework. This module defines the data structures
used to represent validation requests, individual validation findings, schema-
level validation outcomes, and aggregated validation results.

The models establish a consistent contract between validation components,
reporting utilities, and orchestration layers, enabling structured error
tracking, result aggregation, and validation reporting across multiple schema
types and collateral files.

Classes
-------
ValidationRequest
    Represents a validation request containing the schema type, input source,
    and optional schema definition file.

ValidationEntry
    Represents a single validation finding, including validation category,
    affected collateral, status, diagnostic message, and optional location
    information.

SchemaValidationResult
    Represents the validation outcome for an individual schema or collateral,
    including associated validation entries and execution metadata.

ValidationResult
    Represents the aggregated validation results for an execution session,
    enabling consolidation of multiple schema validation outcomes into a
    single reportable structure.

Design Goals
------------
- Provide strongly typed validation result models.
- Standardize reporting across all schema validators.
- Enable structured error, warning, and informational messages.
- Support aggregation of validation results from multiple execution contexts.
- Simplify integration with logging, reporting, and diagnostic frameworks.
- Improve maintainability and extensibility of validation workflows.

This implementation follows PEP 257 documentation guidelines and aligns with
CPACT framework coding standards for consistency, readability, and long-term
maintainability.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------
# Validation Request
# ---------------------------------------------------------------------

@dataclass(slots=True)
class ValidationRequest:
    schema_type: str
    source: str | Path | list[str] | list[Path]
    schema_file: Optional[str] = None


# ---------------------------------------------------------------------
# Validation Entry
# ---------------------------------------------------------------------

@dataclass(slots=True)
class ValidationEntry:
    category: str
    collateral: str
    status: str
    message: str
    path: str = ""
    line: str = ""


# ---------------------------------------------------------------------
# Schema Validation Result (one recipe)
# ---------------------------------------------------------------------

@dataclass(slots=True)
class SchemaValidationResult:

    recipe_name: str

    config_name: str

    map_file: str

    schema_version: str

    recipe_schema_valid: bool

    map_schema_valid: bool

    config_schema_valid: bool

    entries: list[ValidationEntry] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return (
            self.recipe_schema_valid
            and self.map_schema_valid
            and self.config_schema_valid
        )


# ---------------------------------------------------------------------
# Overall Validation Result
# ---------------------------------------------------------------------

@dataclass(slots=True)
class ValidationResult:

    success: bool

    total: int

    passed: int

    failed: int

    results: list[SchemaValidationResult] = field(default_factory=list)