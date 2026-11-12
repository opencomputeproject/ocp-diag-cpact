"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.
This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

===============================================================================
Recipe discovery and listing for the CPACT CLI: finds scenario YAML files under
--test_dir (with metadata filters) and prints them, optionally with connection status.

Extracted from cpact/main.py; cpact.main re-exports these names.
===============================================================================
"""

import argparse
import os
from typing import Any, Dict, List, Optional, Tuple

from tabulate import tabulate

from cpact.utils.custom_exception_handler import CustomExceptionHandler
from cpact.utils.logger_utils import TestLogger
from cpact.utils.path_guard import PathNotAllowedError, resolve_allowed_path
from cpact.utils.scenario_parser import load_yaml_file


def discover_tests(
    test_dir: str,
    filters: Optional[argparse.Namespace],
    logger: Optional[TestLogger] = None,
    errors: Optional[List[str]] = None,
) -> List[str]:
    """
    Discover all supported test files (YAML/YML) recursively and filter by test metadata.

    Args:
        test_dir: Root directory containing test scenarios.
        filters: Parsed argparse namespace with optional fields:
                 test_id (List[str]), test_name (str), test_group (str), tags (List[str]).
                 If None, no filtering is applied.
        logger: Logger instance.
        errors: Optional list that receives the paths of files that failed to parse.

    Returns:
        A list of absolute file paths that match the criteria.
    """
    logger = logger or TestLogger().get_logger()
    matched_tests: List[str] = []

    for root, _, files in os.walk(test_dir):
        for file in files:
            # Keep behavior: only YAML/YML considered (JSON commented in original)
            if not (file.endswith(".yaml") or file.endswith(".yml")):
                continue

            file_path = os.path.join(root, file)
            try:
                data = load_yaml_file(file_path)
                metadata = data.get("test_scenario", {})

                # Apply filters only if provided
                if filters:
                    # test_id: list of accepted IDs
                    if getattr(filters, "test_id", None):
                        if metadata.get("test_id") not in filters.test_id:
                            continue

                    # test_name: substring match (case-insensitive)
                    if getattr(filters, "test_name", None):
                        name = metadata.get("test_name", "")
                        if filters.test_name.lower() not in name.lower():
                            continue

                    # test_group: exact match
                    if getattr(filters, "test_group", None):
                        if filters.test_group != metadata.get("test_group"):
                            continue

                    # tags: intersection with scenario tags
                    if getattr(filters, "tags", None):
                        scenario_tags = set(metadata.get("tags", []))
                        if not scenario_tags.intersection(set(filters.tags)):
                            continue

                matched_tests.append(file_path)

            except Exception as exc:
                CustomExceptionHandler.print_exception(exc)
                logger.error(f"Failed to parse {file_path}: {exc}")
                if errors is not None:
                    errors.append(file_path)
                continue

    return matched_tests


def list_tests(test_files: List[str], logger: Optional[TestLogger] = None) -> None:
    """
    List all discovered test scenarios in a tabular format.

    Args:
        test_files: List of test scenario file paths.
        logger: Logger instance.

    Returns:
        None
    """
    logger = logger or TestLogger().get_logger()

    headers = ["Test ID", "Test Name", "Test Group", "Tags", "Description"]
    skipped_header = ["Test File", "Reason"]
    rows: List[List[str]] = []
    skipped_tests: List[List[str]] = []

    for test_file in test_files:
        logger.info(f"Processing test file: {test_file}")
        scenario_doc = load_yaml_file(test_file)

        if not scenario_doc or "test_scenario" not in scenario_doc:
            # Keep both error lines from original
            logger.error(f"❌ Invalid test scenario in {test_file}. Skipping.")
            logger.error(f"❌ No test scenario found in {test_file}. Skipping.")
            skipped_tests.append(
                [test_file, "No test scenario found or invalid format"]
            )
            continue

        test_scenario = scenario_doc["test_scenario"]
        rows.append(
            [
                str(test_scenario.get("test_id", "")),
                str(test_scenario.get("test_name", "")),
                str(test_scenario.get("test_group", "")),
                ", ".join([str(tag) for tag in test_scenario.get("tags", [])]),
                str(test_scenario.get("description", "")),
            ]
        )

    if rows:
        logger.info("\n" + tabulate(rows, headers=headers, tablefmt="grid"))

    logger.info("=" * 60)
    if skipped_tests:
        logger.info(f"⚠️ Skipped {len(skipped_tests)} invalid test scenarios:")
        logger.info(
            "\n" + tabulate(skipped_tests, headers=skipped_header, tablefmt="grid")
        )


def list_scenarios_with_connections(
    test_files: List[str],
    connections: Dict[str, Any],
    logger: Optional[TestLogger] = None,
) -> List[List[Any]]:
    """
    List all discovered test scenarios along with their connection status in a tabular format.

    Args:
        test_files: List of test scenario file paths.
        connections: Connection configuration dictionary.
        logger: Logger instance.

    Returns:
        A list of lists containing test scenario details and connection status.
    """
    logger = logger or TestLogger().get_logger()

    def get_scenario_connection_details(
        scenario_data: Dict[str, Any],
    ) -> List[Tuple[str, str]]:
        """
        Extract (connection, connection_type) tuples from scenario and nested scenario steps.

        Args:
            scenario_data: Parsed 'test_scenario' dict.

        Returns:
            List of (connection_name, connection_type) tuples.
        """
        details: List[Tuple[str, str]] = []
        scenario_steps = scenario_data.get("test_steps", []) or []

        for step in scenario_steps:
            # Direct connection info
            if "connection" in step and "connection_type" in step:
                details.append((step["connection"], step["connection_type"]))

            # Nested scenario reference
            scenario_path = step.get("scenario_path")
            if scenario_path:
                try:
                    scenario_path = resolve_allowed_path(
                        scenario_path, purpose="scenario_path"
                    )
                except PathNotAllowedError as exc:
                    TestLogger().get_logger().warning(str(exc))
                    continue
            if scenario_path and os.path.exists(scenario_path):
                nested_doc = load_yaml_file(scenario_path)
                nested = nested_doc.get("test_scenario")
                if nested:
                    details.extend(get_scenario_connection_details(nested))
        return details

    def check_scenario_connections(
        scenario_details: List[Tuple[str, str]], conn_config: Dict[str, Any]
    ) -> bool:
        """
        Validate that all required connections exist and are non-empty in the given config.

        Args:
            scenario_details: List of (connection_name, connection_type) pairs.
            conn_config: Connection configuration dictionary.

        Returns:
            True if all connections are valid; False otherwise.
        """
        for conn_name, conn_type in scenario_details:
            c = conn_config.get(conn_name)
            if not c:
                return False
            c_t = c.get(conn_type)
            if c_t in ["N/A", "None", "n/a", "none", "", None]:
                return False
        return True

    headers = [
        "Test ID",
        "Test Name",
        "Test Group",
        "Tags",
        "Description",
        "Executable",
    ]
    rows: List[List[Any]] = []

    for test_file in test_files:
        doc = load_yaml_file(test_file)
        test_scenario = doc.get("test_scenario", {})
        if not test_scenario:
            logger.error(f"❌ No test scenario found in {test_file}. Skipping.")
            continue

        conn_details = get_scenario_connection_details(test_scenario)
        rows.append(
            [
                test_scenario.get("test_id", ""),
                test_scenario.get("test_name", ""),
                test_scenario.get("test_group", ""),
                ", ".join([str(t) for t in test_scenario.get("tags", [])]),
                test_scenario.get("description", ""),
                check_scenario_connections(conn_details, connections),
            ]
        )

    if rows:
        logger.info("\n" + tabulate(rows, headers=headers, tablefmt="grid"))
    return rows
