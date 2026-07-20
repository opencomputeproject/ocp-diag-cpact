"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

===============================================================================
ConfigSchemaValidator is a utility class for validating configuration files against
a defined JSON schema. It extends BaseSchema and uses Draft7Validator to ensure
structural and semantic correctness of configuration data.

Features:
- Loads configuration files in JSON or YAML format.
- Validates configuration structure against a provided schema.
- Logs detailed validation errors including paths and messages.
- Integrates with centralized logging via TestLogger.

Classes:
    ConfigSchemaValidator:
        Extends BaseSchema to support configuration schema validation.

Usage:
    Instantiate ConfigSchemaValidator with a schema dictionary.
    Call `validate_schema(data_file)` to validate a configuration file.
    Review logs for validation success or detailed error messages.
===============================================================================
"""

import os
from jsonschema import Draft7Validator
from tabulate import tabulate
from typing import List, Dict

from cpact.schema_checker.base_schema import BaseSchema
from cpact.result_builder.result_builder import ResultCollector
from cpact.schema_checker import SchemaValidationResult, ValidationEntry


class ConfigSchemaValidator(BaseSchema):
    def __init__(self, schema: dict, schema_dir: str) -> None:
        super().__init__(schema, schema_dir)
        self.report: List[BaseSchema.ReportRow] = []

    def validate_schema(self, data_file: str) -> None:
        """
        Validate the given data against the schema.
        :param data: Data to validate.
        :return: None
        """
        entries: list[ValidationEntry] = []
        data = self.load_schema(data_file)
        validator = Draft7Validator(self.schema)
        errors = sorted(validator.iter_errors(data), key=lambda e: e.path)

        if not errors:
            self.logger.info("✅ Config Schema is valid")
            # rc = ResultCollector().get_instance()
            entries.append(
                ValidationEntry(
                    category="Config Schema",
                    colateral=os.path.basename(data_file),
                    status="SUCCESS",
                    message="Config Schema is valid",
                    path="",
                )
            )
            return SchemaValidationResult(
                recipe_name=data.get("test_scenario", {}).get("test_name", ""),
                map_file=data.get("test_scenario", {}).get("map_file", ""),
                config_name=data_file,
                recipe_schema_valid=False,
                map_schema_valid=False,
                config_schema_valid=True,
                metadata={},
            )

        self.logger.info("❌ Validation error")
        for error in errors:
            path = " : ".join(str(p) for p in error.absolute_path)
            entries.append(
                ValidationEntry(
                    category="Config Schema",
                    file=os.path.basename(data_file),
                    severity="ERROR",
                    message=error.message,
                    path=path,
                )
            )
            if path:
                self.logger.debug(f"   Path: {path}")
            self.logger.info("\n")
        return SchemaValidationResult(
            recipe_name=data.get("test_scenario", {}).get("test_name", ""),
            map_file=data.get("test_scenario", {}).get("map_file", ""),
            config_name=data_file,
            schema_version=data.get("schema_version", ""),
            recipe_schema_valid=False,
            map_schema_valid=False,
            config_schema_valid=(len(errors) == 0),
            entries=entries,
        )
