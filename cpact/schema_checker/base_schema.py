"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.
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
    
    def __init__(self, schema):
        self.schema = self.load_schema(schema)
        self.logger = TestLogger().get_logger()

    def load_file(self, file_name):
        """
        Load a JSON file and return its content.
        :param file_name: Path to the JSON file.
        :return: Parsed JSON data.
        """
        with open(file_name, 'r') as file:
            return json.load(file)
        
    def load_schema(self, schema_file):
        """
        Load the schema from a file.
        :param schema_file: Path to the schema file.
        :return: Parsed schema data.
        """
        schema_type = self.check_schema_type(schema_file)
        if schema_type == 'yaml':
            with open(schema_file, 'r') as file:
                return yaml.safe_load(file)
        elif schema_type == 'json':
            with open(schema_file, 'r') as file:
                return json.load(file)
        else:
            self.logger.error("Unsupported schema file format.")
            return schema_file
    
    def check_schema_type(self, schema_file):
        if schema_file.endswith('.yaml') or schema_file.endswith('.yml'):
            return 'yaml'
        elif schema_file.endswith('.json'):
            return 'json'
        else:
            self.logger.error("Unsupported schema file format.")
            return ""
    
    @abstractmethod
    def validate_schema(self, data_file):
        """
        Validate the given data against the schema.
        This method should be implemented by subclasses.
        """
        raise NotImplementedError("Subclasses must implement this method.")