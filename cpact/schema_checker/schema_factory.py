"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.
"""

import threading
from typing import Dict, Any

from schema_checker.validate_config_schema import ConfigSchemaValidator
from schema_checker.validate_scenario_schema import ScenarioSchemaValidator


EXECUTOR_MAP = {
        "config": ConfigSchemaValidator,
        "scenario": ScenarioSchemaValidator,
    }

class ExecutorFactory:
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, config: Dict[str, Any] = None):
        """Implement Singleton pattern (optional - can be disabled)"""
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(ExecutorFactory, cls).__new__(cls)
        return cls._instance
    
    def __init__(self, schema: Dict[str, Any] = None):
        # Only initialize once
        if not hasattr(self, 'initialized'):
            self.schema = schema or {}
            self.initialized = True
        elif schema:
            # Update schema if provided
            self.schema = schema

    @classmethod
    def get_instance(cls, schema: Dict[str, Any] = None) -> 'ExecutorFactory':
        """Get singleton instance"""
        return cls(schema)
    
    @classmethod
    def reset_instance(cls):
        """Reset singleton instance (useful for testing)"""
        with cls._lock:
            if cls._instance:
                cls._instance.close_all_connections()
            cls._instance = None
    
    def get_executor(self, schema_type: str):
        executor_cls = EXECUTOR_MAP.get(schema_type)
        if not executor_cls:
            raise ValueError(f"No executor found for schema type: {schema_type}")
        return executor_cls