"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.
===================================================================

schema_factory.py

Provides a centralized factory implementation for creating and retrieving
schema validator instances based on the specified schema type.

The factory maintains a mapping between supported schema types and their
corresponding validator classes, enabling extensible and consistent schema
validation throughout the application. This design promotes separation of
concerns and simplifies validator selection logic by encapsulating object
creation within a single location.

Supported schema types:
    - config   : Configuration schema validation
    - scenario : Scenario schema validation

Classes:
    ExecutorFactory: Factory class responsible for returning the appropriate
                     schema validator class for a given schema type.

Raises:
    ValueError: If an unsupported schema type is requested.

"""

from dataclasses import dataclass, field


@dataclass
class ValidationContext:
    schema_type: str
    schema_version: str
    schema_dir: str
    schema_file: str


@dataclass
class SchemaValidationResult:
    recipe_schema_valid: bool
    map_schema_valid: bool
    config_schema_valid: bool
    metadata: dict = field(default_factory=dict)
