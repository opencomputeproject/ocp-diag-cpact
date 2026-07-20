"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.
===================================================================

validation_request.py

Defines the request model used by the schema validation framework.

This module provides a standardized data structure for passing validation
inputs to schema validators and orchestration components. The request model
supports multiple source formats, enabling validation of schema content
originating from files, directories, dictionaries, or collections of
documents. By centralizing request information in a single object, the
framework ensures consistency, extensibility, and simplified validator
integration.

Supported source types:
    - File path (str or Path)
    - In-memory dictionary representation
    - List of file paths
    - List of dictionaries representing schema content

Classes:
    ValidationRequest:
        Encapsulates all information required to initiate a schema
        validation operation, including the source data, schema type,
        and optional schema definition file.

Design Goals:
    - Provide a strongly typed validation request contract.
    - Standardize validator input handling across schema types.
    - Support both file-based and in-memory validation workflows.
    - Simplify request processing and future extensibility.

The implementation follows PEP 257 documentation conventions and aligns
with CPACT framework coding standards.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ValidationRequest:
    """
    Represents a schema validation request.

    Attributes:
        source:
            Input data to be validated. Can be provided as a file path,
            directory path, dictionary object, or a collection of paths
            and dictionaries.

        schema_type:
            Identifier of the schema category to validate
            (for example, "config" or "scenario").

        schema_file:
            Optional schema definition file used during validation.
    """

    source: str | Path | dict[str, Any] | list[str] | list[Path] | list[dict[str, Any]]

    schema_type: str
    schema_file: str | None = None
