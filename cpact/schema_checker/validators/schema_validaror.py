"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.
==============================================================================

Provides the primary schema validation orchestration engine for the
CPACT Schema Validation Framework.

This module coordinates the end-to-end schema validation workflow by
validating requests, resolving schema resources, selecting the
appropriate schema validator implementation, and aggregating validation
results into a standardized response model.

The validator supports multiple schema categories and automatically
determines the appropriate schema version from the input source when
available. Schema-specific validation logic is delegated to specialized
validator implementations through the factory pattern, ensuring
separation of concerns and extensibility.

Responsibilities:
    - Validate schema validation requests.
    - Normalize input sources for processing.
    - Resolve schema directories and schema definition files.
    - Select schema-specific validator implementations.
    - Execute schema validation workflows.
    - Aggregate validation outcomes into a unified result object.

Supported Schema Types:
    - config
    - scenario

Classes:
    SchemaValidator:
        Primary orchestration class responsible for executing schema
        validation operations.

Design Goals:
    - Centralize validation workflow management.
    - Support multiple schema validation strategies.
    - Promote extensibility through factory-based validator selection.
    - Standardize validation result generation.
    - Simplify integration with reporting and automation frameworks.

Implementation follows PEP 257 documentation standards and aligns with
CPACT framework coding conventions.
"""

from pathlib import Path

from cpact.utils.scenario_parser import load_yaml_file

from cpact.schema_checker import (
    ValidationRequest,
    ValidationResult,
    SchemaValidationResult,
)

from cpact.schema_checker.factories.schema_factory import ExecutorFactory
from cpact.schema_checker.utils.schema_utils import SchemaUtils


class SchemaValidator:
    """
    Orchestrates schema validation operations for supported schema types.

    This class serves as the primary entry point for schema validation.
    It validates incoming requests, resolves required schema resources,
    delegates validation to the appropriate validator implementation,
    and aggregates results into a standardized validation response.

    Attributes:
        VALID_TYPES (set[str]):
            Collection of supported schema types that can be validated.

    Responsibilities:
        - Validate request metadata.
        - Normalize validation sources.
        - Resolve schema versions and schema files.
        - Instantiate schema-specific validators.
        - Aggregate validation outcomes.
        - Return structured validation results.

    Supported Schema Types:
        - config
        - scenario
    """


    VALID_TYPES = {"config", "scenario"}

    def validate(
        self,
        request: ValidationRequest,
    ) -> ValidationResult:

        self._validate_request(request)

        results: list[SchemaValidationResult] = []

        for source in self._normalize(request.source):

            result = self._validate_source(
                source,
                request.schema_type,
                request.schema_file,
            )

            results.append(result)

        passed = sum(result.passed for result in results)

        return ValidationResult(
            success=(passed == len(results)),
            total=len(results),
            passed=passed,
            failed=len(results) - passed,
            results=results,
        )

    def _normalize(self, source):
        """
        Normalize validation input into a list structure.

        Ensures downstream processing can uniformly iterate over
        validation sources regardless of whether a single source or
        collection of sources was supplied.

        Args:
            source:
                Validation source or collection of validation sources.

        Returns:
            list:
                Normalized list of validation sources.
        """

        if isinstance(source, list):
            return source

        return [source]

    def _validate_request(
        self,
        request: ValidationRequest,
    ):
        """
        Validate schema validation request parameters.

        Verifies that the requested schema type is supported before
        validation processing begins.

        Args:
            request (ValidationRequest):
                Validation request to verify.

        Raises:
            ValueError:
                If the provided schema type is not supported.
        """

        if request.schema_type not in self.VALID_TYPES:
            raise ValueError(
                f"schema_type must be one of {self.VALID_TYPES}"
            )

    def _validate_source(
        self,
        source,
        schema_type,
        schema_file,
    ) -> SchemaValidationResult:
        """
        Validate a single source against the specified schema.

        Loads the source content, resolves the appropriate schema version,
        determines the schema definition file, instantiates the required
        validator implementation, and executes schema validation.

        Args:
            source (str | Path):
                Path to the source file being validated.

            schema_type (str):
                Schema category to validate against.

            schema_file (str | None):
                Optional explicit schema definition file. If not provided,
                the framework resolves the schema file automatically.

        Returns:
            SchemaValidationResult:
                Validation outcome for the supplied source.

        Raises:
            TypeError:
                If the source is not a supported file path type.

            FileNotFoundError:
                If the source file or schema file cannot be located.

            ValueError:
                If schema resolution fails or invalid schema metadata
                is encountered.
        """

        if not isinstance(source, (str, Path)):
            raise TypeError(
                f"Unsupported source type: {type(source)}"
            )

        data = load_yaml_file(str(source))

        schema_version = (
            data.get("test_scenario", {})
            .get("schema_version")
        )

        schema_dir = SchemaUtils.get_schema_dir(schema_version)

        schema_path = (
            schema_file
            or SchemaUtils.get_schema_file(
                schema_dir,
                schema_type,
            )
        )

        executor_cls = ExecutorFactory.get_executor(
            schema_type
        )

        executor = executor_cls(
            schema_path,
            schema_dir,
        )

        return executor.validate_schema(
            str(source),
        )