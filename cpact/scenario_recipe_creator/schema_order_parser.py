"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

===============================================================================
SchemaOrderParser is a utility class for extracting and preserving the order of properties
defined in a JSON schema. It supports nested structures, conditional logic, and variant schemas,
making it suitable for organizing complex test scenario data in a consistent and predictable format.

Features:
- Parses schema from a dictionary or file path.
- Recursively extracts property order from nested objects, arrays, and conditional blocks.
- Supports ordering for diagnostic analysis variants, test steps, and Docker containers.
- Provides utilities to reorder dictionaries and entire test scenarios based on schema-defined order.

Attributes:
    schema (dict): The loaded JSON schema.
    property_orders (dict): A mapping of schema sections to their ordered property lists.

Usage:
    Instantiate SchemaOrderParser with a schema to extract and apply property ordering.
    Use `order_dict()` or `order_test_scenario()` to reorder data structures before export or display.
===============================================================================
"""

import json
from collections import OrderedDict
from typing import Dict, List, Any, Optional


class SchemaOrderParser:
    """
    Parse property ordering directly from JSON schema.
    Extracts property order based on the order they appear in the schema's 'properties' objects.
    """

    def __init__(self, schema: Dict[str, Any] = None, schema_path: str = None) -> None:
        """
        Initialize with either a schema dict or path to schema file.

        Args:
            schema (dict): JSON schema as dictionary
            schema_path (str): Path to JSON schema file

        Returns:
            None
        """
        if schema:
            self.schema = schema
        elif schema_path:
            with open(schema_path, "r") as f:
                self.schema = json.load(f)
        else:
            raise ValueError("Either schema dict or schema_path must be provided")

        self.property_orders = {}
        self._parse_schema()

    def _parse_schema(self) -> None:
        """
        Parses the loaded schema and extracts property ordering from its structure.

        Args:
            self (SchemaOrderParser): The instance of the SchemaOrderParser class.

        Returns:
            None
        """

        self._extract_property_order(self.schema, "root")

    def _extract_property_order(
        self, schema_section: Dict[str, Any], section_name: str
    ) -> None:
        """
        Recursively extract property orders from schema section.

        Args:
            schema_section (dict): Section of the schema to parse
            section_name (str): Name identifier for this section
        Returns:
            None
        """
        if "properties" in schema_section:
            # Extract property names in the order they appear
            self.property_orders[section_name] = list(
                schema_section["properties"].keys()
            )

            # Recursively parse nested properties
            for prop_name, prop_schema in schema_section["properties"].items():
                if isinstance(prop_schema, dict):
                    if "properties" in prop_schema:
                        # Direct nested properties
                        self._extract_property_order(prop_schema, prop_name)
                    elif "items" in prop_schema and isinstance(
                        prop_schema["items"], dict
                    ):
                        # Array items with properties
                        if "properties" in prop_schema["items"]:
                            self._extract_property_order(
                                prop_schema["items"], f"{prop_name}_item"
                            )
                        elif "oneOf" in prop_schema["items"]:
                            # Handle oneOf in array items (like diagnostic_analysis)
                            for i, one_of_schema in enumerate(
                                prop_schema["items"]["oneOf"]
                            ):
                                if "properties" in one_of_schema:
                                    self._extract_property_order(
                                        one_of_schema, f"{prop_name}_variant_{i+1}"
                                    )

        # Handle conditional schemas (allOf with if/then)
        if "allOf" in schema_section:
            for i, condition in enumerate(schema_section["allOf"]):
                if "then" in condition and "properties" in condition["then"]:
                    # Extract step type from the if condition
                    if_condition = condition.get("if", {})
                    step_type = None
                    if (
                        "properties" in if_condition
                        and "step_type" in if_condition["properties"]
                    ):
                        step_type_schema = if_condition["properties"]["step_type"]
                        if "const" in step_type_schema:
                            step_type = step_type_schema["const"]

                    if step_type:
                        self._extract_property_order(condition["then"], step_type)
                    else:
                        self._extract_property_order(
                            condition["then"], f"condition_{i}"
                        )

    def get_order(self, section: str) -> List[str]:
        """
        Get property order for a specific section.

        Args:
            section (str): Section name

        Returns:
            List[str]: List of property names in order
        """
        return self.property_orders.get(section, [])

    def get_step_order(self, step_type: str) -> List[str]:
        """
        Get complete property order for a test step based on its type.

        Args:
            step_type (str): Type of test step

        Returns:
            List[str]: Ordered list of property names
        """
        # Get base test_steps properties (from the items schema)
        base_order = self.get_order("test_steps_item")

        # Get step-type-specific properties
        specific_order = self.get_order(step_type)

        # Combine base and specific properties
        combined_order = base_order.copy()
        for prop in specific_order:
            if prop not in combined_order:
                combined_order.append(prop)

        return combined_order

    def get_diagnostic_analysis_order(
        self, diagnostic_item: Dict[str, Any]
    ) -> List[str]:
        """
        Determine the correct property order for a diagnostic analysis item.

        Args:
            diagnostic_item (dict): Diagnostic analysis item

        Returns:
            List[str]: Ordered list of property names
        """
        if "search_string" in diagnostic_item:
            return self.get_order("diagnostic_analysis_variant_1")
        elif "diagnostic_search_string" in diagnostic_item:
            return self.get_order("diagnostic_analysis_variant_2")
        elif "search_code" in diagnostic_item:
            return self.get_order("diagnostic_analysis_variant_3")
        else:
            # Default to first variant
            return self.get_order("diagnostic_analysis_variant_1")

    def order_dict(
        self, data: Dict[str, Any], property_order: List[str]
    ) -> OrderedDict:
        """
        Order a dictionary according to the specified property order.

        Args:
            data (dict): Dictionary to order
            property_order (list): List of property names in desired order

        Returns:
            OrderedDict: Ordered dictionary
        """
        ordered_dict = OrderedDict()

        # Add properties in the specified order
        for prop in property_order:
            if prop in data:
                ordered_dict[prop] = data[prop]

        # Add any remaining properties not in the order list
        for key, value in data.items():
            if key not in ordered_dict:
                ordered_dict[key] = value

        return ordered_dict

    def order_test_scenario(self, test_scenario_dict: Dict[str, Any]) -> OrderedDict:
        """
        Order a complete test scenario dictionary according to schema order.

        Args:
            test_scenario_dict (dict): Test scenario dictionary

        Returns:
            OrderedDict: Fully ordered test scenario
        """
        # Order main test scenario
        scenario_order = self.get_order("test_scenario")
        ordered_scenario = self.order_dict(test_scenario_dict, scenario_order)

        # Order docker containers if present
        if "docker" in ordered_scenario and ordered_scenario["docker"]:
            docker_order = self.get_order("docker_item")
            ordered_docker = []
            for container in ordered_scenario["docker"]:
                ordered_container = self.order_dict(container, docker_order)
                ordered_docker.append(ordered_container)
            ordered_scenario["docker"] = ordered_docker

        # Order test steps if present
        if "test_steps" in ordered_scenario and ordered_scenario["test_steps"]:
            ordered_steps = []
            for step in ordered_scenario["test_steps"]:
                step_type = step.get("step_type", "")
                step_order = self.get_step_order(step_type)
                ordered_step = self.order_dict(step, step_order)

                # Order entry_criteria if present
                if "entry_criteria" in ordered_step and ordered_step["entry_criteria"]:
                    entry_criteria_order = self.get_order("entry_criteria_item")
                    ordered_criteria = []
                    for criteria in ordered_step["entry_criteria"]:
                        ordered_criteria.append(
                            self.order_dict(criteria, entry_criteria_order)
                        )
                    ordered_step["entry_criteria"] = ordered_criteria

                # Order output_analysis if present
                if (
                    "output_analysis" in ordered_step
                    and ordered_step["output_analysis"]
                ):
                    output_analysis_order = self.get_order("output_analysis_item")
                    ordered_analysis = []
                    for analysis in ordered_step["output_analysis"]:
                        ordered_analysis.append(
                            self.order_dict(analysis, output_analysis_order)
                        )
                    ordered_step["output_analysis"] = ordered_analysis

                # Order diagnostic_analysis if present
                if (
                    "diagnostic_analysis" in ordered_step
                    and ordered_step["diagnostic_analysis"]
                ):
                    ordered_diagnostics = []
                    for diagnostic in ordered_step["diagnostic_analysis"]:
                        diagnostic_order = self.get_diagnostic_analysis_order(
                            diagnostic
                        )
                        ordered_diagnostics.append(
                            self.order_dict(diagnostic, diagnostic_order)
                        )
                    ordered_step["diagnostic_analysis"] = ordered_diagnostics

                ordered_steps.append(ordered_step)
            ordered_scenario["test_steps"] = ordered_steps

        return ordered_scenario

    def print_extracted_orders(self) -> None:
        """
        Prints all extracted property orders for debugging purposes.

        Args:
            self (SchemaOrderParser): The instance of the SchemaOrderParser class.

        Returns:
            None
        """
        print("Extracted Property Orders:")
        print("=" * 50)
        for section, order in self.property_orders.items():
            print(f"{section}: {order}")
        print("=" * 50)
