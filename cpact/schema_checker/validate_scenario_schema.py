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
import os
from pathlib import Path
import re
from packaging import version

from cpact.utils.path_resolver import resolve_paths_in_yaml
from cpact.schema_checker.base_schema import BaseSchema


class ScenarioSchemaValidator(BaseSchema):
    def __init__(self, schema: dict, schema_dir: str) -> None:
        """
        Initializes the ScenarioSchemaValidator with a schema file or dictionary.
        Args:
            schema (str or dict): The schema file path or dictionary.
        Returns:
            None
        """
        super().__init__(schema, schema_dir)

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
        self.logger.info(f"Validating {data_file} against scenario schema...")
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
            return False
        # Validate the data against the schema
        validator = Draft7Validator(self.schema)
        errors = sorted(validator.iter_errors(data), key=lambda e: e.path)
        if errors:
            self.logger.error("❌ Scenario Schema validation FAILED")
            for error in errors:
                path = " : ".join(str(p) for p in error.absolute_path)
                self.logger.error(f" * {error.message}")
                if path:
                    self.logger.error(f"   Path: {path}\n")
            return False
        self.logger.info("✅ Scenario Schema is valid")

        self.logger.info("🔍 Starting MAP Schema Validation...")

        scenario_data = data.get("test_scenario", {})
        map_schema_validate = True
        scenario_data, _ = resolve_paths_in_yaml(scenario_data)

        if scenario_data and scenario_data.get("map_file"):
            scenario_map_file = scenario_data.get("map_file")
            scenario_dir = os.path.dirname(os.path.abspath(data_file))
            if os.path.dirname(scenario_map_file):
                resolved_map_file = scenario_map_file
            else:
                resolved_map_file = os.path.join(scenario_dir, scenario_map_file)
            self.logger.info(f"📍 Resolved map file absolute path: {resolved_map_file}")

            map_res = self.validate_map_schema(resolved_map_file)
            self.logger.info(f"map_file detected in YAML: {resolved_map_file}")
            if not map_res:
                self.logger.error(f"❌ Map file validation FAILED: {resolved_map_file}")
                return False
        
        return True
    
    def validate_map_schema(self, map_file_path: str) -> bool:
        """
        Validate the map JSON file against the latest map_recipe_schema_*.json.
        """

        self.logger.info(f"📍 Attempting to load map file from: {os.path.abspath(map_file_path)}")        
        try:
            map_data = self.load_schema(map_file_path)
        except Exception as e:
            self.logger.error(f"❌ Failed to load map file '{map_file_path}': {e}")
            return False
        try:
            spec_schema_dir = self.schema_dir
        except Exception as e:
            self.logger.error(f"❌ Failed to resolve schema directory: {e}")
            return False

        # if not self.schema_dir.exists():
        #     self.logger.error(f"❌ Schema directory not found: {self.schema_dir}")
        #     return False

        # Find files like map_file_schema_0.7.json, map_file_schema_1.2.json
        map_schema_file = os.path.join(spec_schema_dir, "map_recipe_schema.json")
        if not map_schema_file:
            self.logger.error(f"❌ No map recipe schemas found in: {self.schema_dir}")
            return False

        # versioned_files = []
        # pattern = re.compile(r"map_file_schema_(\d+(?:\.\d+)*).json")

        # for file in schema_files:
        #     match = pattern.search(file.name)
        #     if match:
        #         try:
        #             ver = version.parse(match.group(1))
        #             versioned_files.append((ver, file))
        #         except Exception:
        #             continue

        # if not versioned_files:
        #     self.logger.error("❌ No valid versioned map schema files detected!")
        #     return False

        # # Pick highest version
        # latest_version, map_schema_path = max(versioned_files, key=lambda x: x[0])

        # self.logger.info(
        #     f"📌 Auto-selected latest MAP schema: {map_schema_path.name} (v{latest_version})"
        # )

        try:
            map_schema = self.load_schema(map_schema_file)
        except Exception as e:
            self.logger.error(f"❌ Failed to load map schema '{map_schema_file}': {e}")
            return False

        validator = Draft7Validator(map_schema)
        errors = sorted(validator.iter_errors(map_data), key=lambda e: e.path)

        if not errors:
            self.logger.info("✅ Scenario Schema is valid")
            return True

        self.logger.error(f"❌ Map Schema validation FAILED: {map_file_path}")
        for error in errors:
            path = " : ".join(str(p) for p in error.absolute_path)
            self.logger.error(f" * {error.message}")
            if path:
                self.logger.error(f"   Path: {path}\n")

        return False


    # def _load_scenario_file(self, file_path: str) -> dict:
    #     """
    #     Load a scenario file (YAML format).
    #     :param file_path: Path to the scenario file.
    #     :return: Parsed scenario data.
    #     """
    #     yaml = YAML(typ="rt")
    #     with open(file_path, "r", encoding="utf-8") as file:
    #         return yaml.load(file)
        