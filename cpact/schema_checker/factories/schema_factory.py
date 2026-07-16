"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

===========================================================================================
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

from cpact.schema_checker.validators.validate_config_schema import ConfigSchemaValidator
from cpact.schema_checker.validators.validate_scenario_schema import (
    ScenarioSchemaValidator,
)


class ExecutorFactory:

    EXECUTOR_MAP = {
        "config": ConfigSchemaValidator,
        "scenario": ScenarioSchemaValidator,
    }

    @classmethod
    def get_executor(cls, schema_type: str):

        executor = cls.EXECUTOR_MAP.get(schema_type)

        if executor is None:
            raise ValueError(f"Unsupported schema type: {schema_type}")

        return executor
