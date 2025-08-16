"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.
"""

from jsonschema import Draft7Validator

from schema_checker.base_schema import BaseSchema

class ConfigSchemaValidator(BaseSchema):
    def __init__(self, schema):
        super().__init__(schema)
        
    def validate_schema(self, data_file):
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
