"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

===============================================================================
BaseSchema is an abstract base class for schema validation utilities. It provides
common functionality for loading and identifying schema files in JSON or YAML format,
and integrates with a centralized logging system for consistent diagnostics.

Features:
- Loads schema files from JSON or YAML formats.
- Automatically detects schema type based on file extension.
- Provides a unified interface for schema validation.
- Designed to be extended by specific schema validator implementations.
- Integrates with TestLogger for structured logging.

Classes:
    BaseSchema:
        Abstract base class for schema validation logic.
        Must be subclassed with an implementation of `validate_schema`.

Usage:
    Subclass BaseSchema to implement custom validation logic.
    Use `load_schema()` to load schema files.
    Override `validate_schema()` to define validation behavior.
===============================================================================
"""
import json
import yaml
from abc import ABC, abstractmethod

from utils.logger_utils import TestLogger


class BaseSchema(ABC):
    """
    Base class for schema validation.
    This class should be inherited by all schema classes.
    """

    def __init__(self, schema: dict) -> None:
        """
        Initializes the BaseSchema with a schema file or dictionary.
        Args:
            schema (str or dict): The schema file path or dictionary.
        Returns:
            None
        """
        self.schema = self.load_schema(schema)
        self.logger = TestLogger().get_logger()

    def load_file(self, file_name: str) -> dict:
        """
        Load a JSON file and return its content.
        :param file_name: Path to the JSON file.
        :return: Parsed JSON data.
        """
        with open(file_name, "r") as file:
            return json.load(file)

    def load_schema(self, schema_file: str) -> dict:
        """
        Load the schema from a file.
        :param schema_file: Path to the schema file.
        :return: Parsed schema data.
        """
        schema_type = self.check_schema_type(schema_file)
        if schema_type == "yaml":
            with open(schema_file, "r") as file:
                return yaml.safe_load(file)
        elif schema_type == "json":
            with open(schema_file, "r") as file:
                return json.load(file)
        else:
            self.logger.error("Unsupported schema file format.")
            return schema_file

    def check_schema_type(self, schema_file: str) -> str:
        """
        Check the schema file type based on its extension.
        :param schema_file: Path to the schema file.
        :return: 'yaml' or 'json' based on the file extension.
        """
        if schema_file.endswith(".yaml") or schema_file.endswith(".yml"):
            return "yaml"
        elif schema_file.endswith(".json"):
            return "json"
        else:
            self.logger.error("Unsupported schema file format.")
            return ""

    @abstractmethod
    def validate_schema(self, data_file: dict) -> bool:
        """
        Validate the given data against the schema.
        This method should be implemented by subclasses.
        """
        raise NotImplementedError("Subclasses must implement this method.")
