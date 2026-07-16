"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree
===================================================================
Provides the public schema validation service interface for the
CPACT Schema Validation Framework.

This module serves as the primary entry point for schema validation
operations. It coordinates validation execution, result aggregation,
and report generation while abstracting underlying validator and
reporting implementations from consumers.

The service layer follows a facade pattern, providing a simple and
consistent API for validating schema-based documents without requiring
callers to manage validator selection, report publishing, or result
processing directly.

Features:
    - Centralized schema validation entry point.
    - Validation request orchestration.
    - Automatic report generation and publishing.
    - Standardized validation result handling.
    - Integration with framework logging infrastructure.
    - Separation of validation and reporting concerns.

Classes:
    SchemaService:
        Service layer responsible for coordinating validation
        and reporting operations.

Design Goals:
    - Simplify schema validation workflows.
    - Provide a clean public validation API.
    - Centralize orchestration logic.
    - Promote maintainability and extensibility.
    - Support integration with automation and CI/CD systems.

Implementation follows PEP 257 documentation conventions and aligns
with CPACT framework coding standards.
"""

from cpact.utils.logger_utils import TestLogger

from cpact.schema_checker import ValidationResult, ValidationRequest

from cpact.schema_checker.validators.schema_validaror import SchemaValidator
from cpact.schema_checker.reports.schema_reports import SchemaReporter


class SchemaService:
    """
    Public facade for schema validation operations.

    This service coordinates schema validation execution and
    reporting activities. It acts as the primary interface
    for consumers of the schema validation framework by
    encapsulating validator and reporting dependencies behind
    a simplified API.

    Attributes:
        logger:
            Logger instance used for validation and reporting
            activities.

        validator (SchemaValidator):
            Validation engine responsible for executing schema
            validation workflows.

        reporter (SchemaReporter):
            Reporting component responsible for publishing
            validation results.

    Responsibilities:
        - Accept validation requests.
        - Execute schema validation workflows.
        - Coordinate report generation.
        - Return standardized validation results.
        - Provide a simplified public API.
    """

    def __init__(self, logger=None):

        self.logger = logger or TestLogger().get_logger()

        self.validator = SchemaValidator()

        self.reporter = SchemaReporter(
            logger=self.logger
        )

    def validate(
        self,
        request: ValidationRequest,
        publish_report=True,
    ) -> ValidationResult:

        result = self.validator.validate(request)

        if publish_report:
            self.reporter.publish(result)

        return result