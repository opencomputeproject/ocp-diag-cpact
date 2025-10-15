"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

===============================================================================
ExecutorFactory is a singleton-based factory class for managing schema validation executors.
It dynamically returns the appropriate validator class based on the schema type, supporting
both configuration and scenario schema validation workflows.

Features:
- Implements a thread-safe singleton pattern for consistent executor access.
- Maps schema types to their corresponding validator classes.
- Supports dynamic schema injection and updates.
- Provides centralized access to ConfigSchemaValidator and ScenarioSchemaValidator.
- Allows resetting the factory instance for testing or reinitialization.

Classes:
    ExecutorFactory:
        Manages executor selection and lifecycle for schema validation.

Supported Schema Types:
    - "config": Uses ConfigSchemaValidator
    - "scenario": Uses ScenarioSchemaValidator

Usage:
    Use `ExecutorFactory.get_instance(schema)` to initialize or retrieve the factory.
    Call `get_executor(schema_type)` to retrieve the appropriate validator class.
    Use `reset_instance()` to clear the factory state when needed.
===============================================================================
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

    def __new__(cls, config: Dict[str, Any] = None) -> "ExecutorFactory":
        """Implement Singleton pattern (optional - can be disabled)"""
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(ExecutorFactory, cls).__new__(cls)
        return cls._instance

    def __init__(self, schema: Dict[str, Any] = None) -> None:
        """Initialize the factory with optional schema (only once)"""
        # Only initialize once
        if not hasattr(self, "initialized"):
            self.schema = schema or {}
            self.initialized = True
        elif schema:
            # Update schema if provided
            self.schema = schema

    @classmethod
    def get_instance(cls, schema: Dict[str, Any] = None) -> "ExecutorFactory":
        """Get singleton instance"""
        return cls(schema)

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton instance (useful for testing)"""
        with cls._lock:
            if cls._instance:
                cls._instance.close_all_connections()
            cls._instance = None

    def get_executor(self, schema_type: str) -> type:
        """
        Returns the executor class based on the schema type.
        Args:
            schema_type (str): The type of the schema to be validated.
        Returns:
            type: The executor class corresponding to the schema type.
        """
        executor_cls = EXECUTOR_MAP.get(schema_type)
        if not executor_cls:
            raise ValueError(f"No executor found for schema type: {schema_type}")
        return executor_cls
