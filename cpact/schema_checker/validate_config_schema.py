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

from jsonschema import Draft7Validator

from schema_checker.base_schema import BaseSchema


class ConfigSchemaValidator(BaseSchema):
    def __init__(self, schema: dict) -> None:
        super().__init__(schema)

    def validate_schema(self, data_file: str) -> None:
        """
        Validate the given data against the schema.
        :param data: Data to validate.
        :return: None
        """
        data = self.load_schema(data_file)
        validator = Draft7Validator(self.schema)
        errors = sorted(validator.iter_errors(data), key=lambda e: e.path)

        if not errors:
            self.logger.info("✅ Config Schema is valid")
            return

        self.logger.info("❌ Validation error")
        for error in errors:
            path = " : ".join(str(p) for p in error.absolute_path)
            self.logger.info(f" * {error.message}")
            if path:
                self.logger.info(f"   Path: {path}")
            self.logger.info("\n")
