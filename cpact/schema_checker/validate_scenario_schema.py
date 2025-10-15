"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

===============================================================================
ScenarioSchemaValidator is a schema validation utility for YAML-based test scenarios.
It extends BaseSchema and provides enhanced validation features including duplicate key
detection and JSON Schema compliance checks using Draft7Validator.

Features:
- Scans YAML files for duplicate keys and reports line-level warnings.
- Loads YAML files with support for duplicate keys using ruamel.yaml.
- Validates scenario data against a provided JSON schema.
- Logs validation results with detailed error paths and messages.
- Integrates with centralized logging via TestLogger.

Classes:
    ScenarioSchemaValidator:
        Extends BaseSchema to support YAML schema validation and duplicate key detection.

Usage:
    Instantiate ScenarioSchemaValidator with a schema dictionary.
    Call `validate_schema(data_file)` to validate a YAML scenario file.
    Use `scan_duplicates()` to detect duplicate keys before parsing.
===============================================================================
"""
from jsonschema import Draft7Validator
from collections import defaultdict
from ruamel.yaml import YAML


from schema_checker.base_schema import BaseSchema


class ScenarioSchemaValidator(BaseSchema):
    def __init__(self, schema: dict) -> None:
        """
        Initializes the ScenarioSchemaValidator with a schema file or dictionary.
        Args:
            schema (str or dict): The schema file path or dictionary.
        Returns:
            None
        """
        super().__init__(schema)

    def scan_duplicates(self, yaml_file: str) -> list:
        """
        Scan a YAML file for duplicate keys.
        Args:
            yaml_file (str): Path to the YAML file.
        Returns:
            list: A list of warnings about duplicate keys.
        """
        duplicates = []
        stack = [defaultdict(int)]
        indent_level = [0]

        with open(yaml_file, "r", encoding="utf-8") as file:
            for line_num, line in enumerate(file, start=1):
                stripped_line = line.strip()
                if not stripped_line or stripped_line.startswith("#"):
                    continue

                current_indent = len(line) - len(stripped_line)
                while indent_level and current_indent < indent_level[-1]:
                    stack.pop()
                    indent_level.pop()

                if stripped_line.startswith("-"):
                    stack.append(defaultdict(int))
                    indent_level.append(current_indent + 1)
                    stripped_line = stripped_line[2:].strip()
                if ":" in stripped_line:
                    key = stripped_line.split(":", 1)[0].strip()
                    if key in stack[-1]:
                        duplicates.append(f"Duplicate key '{key}' found at line {line}")
                    stack[-1][key] += 1
                    if stripped_line.endswith(":"):
                        stack.append(defaultdict(int))
                        indent_level.append(current_indent + 1)
        return duplicates

    def load_yaml_with_duplicates(self, yaml_file: str) -> dict:
        """
        Load a YAML file and check for duplicate keys.
        :param yaml_file: Path to the YAML file.
        :return: Parsed YAML data.
        """
        yaml = YAML(typ="rt")
        if hasattr(yaml, "allow_duplicate_keys"):
            yaml.allow_duplicate_keys = True
        with open(yaml_file, "r", encoding="utf-8") as file:
            return yaml.load(file)

    def validate_schema(self, data_file: str) -> None:
        """
        Validate the given data against the schema.
        :param data: Data to validate.
        :return: None
        """
        # Check the duplicate keys in the YAML file
        duplicate_warnings = self.scan_duplicates(data_file)
        if duplicate_warnings:
            self.logger.warning("Duplicate keys found in the YAML file:")
            for warning in duplicate_warnings:
                self.logger.warning(f" * {warning}")

        # Load the YAML file with duplicate keys allowed
        try:
            data = self.load_yaml_with_duplicates(data_file)
        except Exception as e:
            self.logger.error(f"Failed to load YAML file: {e}")
            return

        # Validate the data against the schema
        validator = Draft7Validator(self.schema)
        errors = sorted(validator.iter_errors(data), key=lambda e: e.path)

        if not errors:
            self.logger.info("✅ Scenario Schema is valid")
            return

        self.logger.error("❌ Validation error")
        for error in errors:
            path = " : ".join(str(p) for p in error.absolute_path)
            self.logger.error(f" * {error.message}")
            if path:
                self.logger.error(f"   Path: {path} \n")
