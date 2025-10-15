"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

===============================================================================
TestExecutor is a command-line utility for discovering, validating, and executing YAML/JSON-based
test scenarios. It supports schema validation, connection discovery, and orchestrated test execution
with detailed logging and result reporting.

Features:
- Discovers test scenarios from a directory with metadata filtering.
- Validates scenarios and configuration files against JSON schemas.
- Tests connectivity for all configured connection types (SSH, Redfish, Local).
- Executes test scenarios using the Orchestrator engine.
- Collects and prints detailed results, diagnostics, and execution summaries.
- Supports exporting results and connection diagnostics to JSON and CSV.

Components:
    - discover_tests(): Recursively finds valid test files based on filters.
    - run_test(): Executes a single test scenario and logs results.
    - list_tests(): Displays discovered test scenarios in tabular format.
    - list_scenarios_with_connections(): Lists scenarios with connection validation status.
    - discover_and_test_connections(): Discovers and tests all connection combinations.
    - calculate_connection_statistics(): Computes statistics from connection test results.
    - validate_schema(): Validates files or directories against config/scenario schemas.
    - main(): Entry point for CLI argument parsing and execution flow.

Usage:
    Run the script with CLI arguments to list, validate, or execute test scenarios.
    Example:
        python test_executor.py --test_dir ./tests --list
        python test_executor.py --schema_check scenario ./tests/specs
        python test_executor.py --discover_connections --conn_config ./config.json
===============================================================================
"""

import os
import time
import json
import argparse
from tabulate import tabulate
from typing import Dict, List, Any, Type

from utils.logger_utils import TestLogger
from utils.scenario_parser import load_yaml_file
from utils.scenario_parser import load_yaml_file
from result_builder.result_builder import ResultCollector
from schema_checker.schema_factory import ExecutorFactory
from core.orchestrator import Orchestrator as Orchestrator
from system_connections.connection_factory import ConnectionFactory
from system_connections.connection_discovery import ConnectionDiscovery


def discover_tests(test_dir: str, filters: list, logger: Type["TestLogger"] = None) -> List[str]:
    """
    Discover all supported test files (YAML or JSON) recursively and filter by test metadata.
    """
    matched_tests = []

    for root, _, files in os.walk(test_dir):
        for file in files:
            if not (
                file.endswith(".yaml")
                or file.endswith(".yml")
                or file.endswith(".json")
            ):
                continue

            file_path = os.path.join(root, file)

            try:
                data = load_yaml_file(file_path)
                metadata = data.get("test_scenario", {})
                if filters:
                    if filters.test_id and filters.test_id != metadata.get("test_id"):
                        continue
                    if (
                        filters.test_name
                        and filters.test_name.lower()
                        not in metadata.get("test_name", "").lower()
                    ):
                        continue
                    if filters.test_group and filters.test_group != metadata.get(
                        "test_group"
                    ):
                        continue
                    if filters.tags and not set(filters.tags).intersection(
                        set(metadata.get("tags", []))
                    ):
                        continue

                matched_tests.append(file_path)

            except Exception as e:
                if logger:
                    logger.error(f"Failed to parse {file_path}: {e}")
                else:
                    print(f"Failed to parse {file_path}: {e}")
                continue

    return matched_tests


def run_test(file_path: str, workspace: str, logger=None) -> None:
    """
    Run a single test scenario from the given file path.
    :param file_path: Path to the test scenario file.
    :param workspace: Directory for logs and results.
    :param logger: Logger instance for logging.
    :return: None
    """
    import json

    logger.info(f"\n🚀 Running Test: {file_path}")
    scenario_data = load_yaml_file(file_path)
    # with open("scenario.json", 'w') as f:
    #     json.dump(scenario_data, f, indent=2)
    if not scenario_data or "test_scenario" not in scenario_data:
        logger.error(f"❌ Invalid test scenario in {file_path}. Skipping.")
        return

    start_time = time.time()
    orchestrator = Orchestrator()
    orchestrator.run(scenario_data["test_scenario"])
    elapsed_time = time.time() - start_time
    logger.info(f"✅ Test completed in {elapsed_time:.2f} seconds")
    logger.info("---------------------- Test Summary -------------------------")
    ResultCollector().get_instance().print_summary()
    ResultCollector().get_instance().dump_results(
        os.path.join(TestLogger().get_log_dir(), "test_results.json")
    )
    ResultCollector().get_instance().dump_diagnostics(
        os.path.join(TestLogger().get_log_dir(), "diagnostics_codes.json")
    )
    ResultCollector().get_instance().print_summary_table()
    logger.info(f"⏱️ Total execution time: {elapsed_time:.2f}s\n")


def list_tests(test_files: List[str], logger=None) -> None:
    """
    List all discovered test scenarios in a tabular format.
    :param test_files: List of test scenario file paths.
    :param logger: Logger instance for logging.
    :return: None
    """

    headers = ["Test ID", "Test Name", "Test Group", "Tags", "Description"]
    skipped_header = ["Test File", "Reason"]
    rows = []
    skipped_tests = []
    for test_file in test_files:
        scenario_data = load_yaml_file(test_file)
        if logger:
            logger.info(f"Processing test file: {test_file}")
        else:
            print(f"Processing test file: {test_file}")
        if not scenario_data or "test_scenario" not in scenario_data:
            logger.error(f"❌ Invalid test scenario in {test_file}. Skipping.")
            logger.error(f"❌ No test scenario found in {test_file}. Skipping.")
            skipped_tests.append(
                [test_file, "No test scenario found or invalid format"]
            )
            continue
        logger.info(f"Available tests in {test_file}:")
        test_scenario = scenario_data["test_scenario"]
        rows.append(
            [
                test_scenario.get("test_id", ""),
                test_scenario.get("test_name", ""),
                test_scenario.get("test_group", ""),
                ", ".join([str(tag) for tag in test_scenario.get("tags", [])]),
                test_scenario.get("description", ""),
            ]
        )

    logger.info("\n" + tabulate(rows, headers=headers, tablefmt="grid"))

    logger.info("" + "=" * 60)
    if skipped_tests:
        logger.info(f"⚠️ Skipped {len(skipped_tests)} invalid test scenarios:")
        logger.info(
            "\n" + tabulate(skipped_tests, headers=skipped_header, tablefmt="grid")
        )


def list_scenarios_with_connections(
    test_files: List[str], connections: Dict[str, Any], logger=None
) -> List[List[Any]]:
    """
    List all discovered test scenarios along with their connection status in a tabular format.
    Args:
        test_files (List[str]): List of test scenario file paths.
        connections (Dict[str, Any]): Connection configuration dictionary.
        logger: Logger instance for logging.
    Returns:
        List[List[Any]]: A list of lists containing test scenario details and connection status.
    """

    def get_scenario_data(scenario_data, connection_details=[]):
        # scenario_data = load_yaml_file(test_file)
        scenario_steps = scenario_data.get("test_steps", [])
        for step in scenario_steps:
            if "connection" in step and "connection_type" in step:
                connection_details.append((step["connection"], step["connection_type"]))
            if "scenario_path" in step:
                scenario_path = step["scenario_path"]
                if os.path.exists(scenario_path):
                    scenario = load_yaml_file(scenario_path)
                    if "test_scenario" in scenario:
                        get_scenario_data(scenario["test_scenario"], connection_details)

    def check_scenario_connections(
        scenario_connection_details: List[tuple[str, str]], connections: Dict[str, Any]
    ) -> bool:
        """
        Check if all connections in the scenario are valid based on the provided connections dictionary.
        Args:
            scenario_connection_details (List[Tuple[str, str]]): List of tuples containing connection names and types.
            connections (Dict[str, Any]): Connection configuration dictionary.
        Returns:
            bool: True if all connections are valid, False otherwise.
        """
        for connection, connection_type in scenario_connection_details:
            c = connections.get(connection)
            c_t = c.get(connection_type)
            if not c or not c_t:
                return False
            if c and c_t in ["N/A", "None", "n/a", "none", "", None]:
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
    rows = []
    for test_file in test_files:
        connection_details = []
        test_scenario = load_yaml_file(test_file).get("test_scenario", {})
        if not test_scenario:
            logger.error(f"❌ No test scenario found in {test_file}. Skipping.")
            continue
        scenario_data = get_scenario_data(test_scenario, connection_details)
        rows.append(
            [
                test_scenario.get("test_id", ""),
                test_scenario.get("test_name", ""),
                test_scenario.get("test_group", ""),
                ", ".join(test_scenario.get("tags", [])),
                test_scenario.get("description", ""),
                check_scenario_connections(connection_details, connections),
            ]
        )
    if logger:
        logger.info("\n" + tabulate(rows, headers=headers, tablefmt="grid"))
    else:
        print("\n" + tabulate(rows, headers=headers, tablefmt="grid"))
    return rows


def discover_and_test_connections(
    config: Dict[str, Any], timeout: int = 10, export_csv: bool = False
) -> Dict[str, Any]:
    """
    Main function to discover and test all connections from config

    Args:
        config: Connection configuration
        timeout: Timeout for connection tests in seconds
        export_csv: Whether to export results to CSV

    Returns:
        Dict containing test results and statistics
    """
    print("🔍 DISCOVERING ALL POSSIBLE CONNECTIONS...")

    # Create factory and discovery instance
    factory = ConnectionFactory.get_instance(config)
    discovery = ConnectionDiscovery(factory)

    # Discover all connections
    discovery_result = discovery.discover_all_connections()

    print(
        f"📊 Found {discovery_result['total_combinations']} possible connection combinations:"
    )
    print(
        f"   • Connection Names: {', '.join(discovery_result['available_connection_names'])}"
    )
    print(
        f"   • Connection Types: {', '.join(discovery_result['available_connection_types'])}"
    )

    # Test all connections
    print(f"\n🧪 TESTING CONNECTIVITY (timeout: {timeout}s per test)...")
    test_results = discovery.test_all_connections(timeout=timeout)

    # Print results table
    discovery.print_connection_table(test_results)

    # Export to CSV if requested
    if export_csv:
        discovery.export_results_to_csv(test_results)

    # Calculate detailed statistics
    stats = calculate_connection_statistics(test_results)

    # Clean up
    factory.close_all_connections()

    return {
        "discovery": discovery_result,
        "test_results": test_results,
        "statistics": stats,
    }


def calculate_connection_statistics(
    test_results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Calculate detailed statistics from test results"""

    if not test_results:
        return {}

    # Basic counts
    total = len(test_results)
    success_count = len([r for r in test_results if r["status"] == "SUCCESS"])
    partial_count = len([r for r in test_results if r["status"] == "PARTIAL"])
    failed_count = len([r for r in test_results if r["status"] == "FAILED"])
    error_count = len([r for r in test_results if r["status"] == "ERROR"])

    # Statistics by connection type
    type_stats = {}
    for result in test_results:
        conn_type = result["connection_type"]
        if conn_type not in type_stats:
            type_stats[conn_type] = {"total": 0, "success": 0, "failed": 0}

        type_stats[conn_type]["total"] += 1
        if result["status"] == "SUCCESS":
            type_stats[conn_type]["success"] += 1
        else:
            type_stats[conn_type]["failed"] += 1

    # Statistics by connection name
    name_stats = {}
    for result in test_results:
        conn_name = result["connection_name"]
        if conn_name not in name_stats:
            name_stats[conn_name] = {"total": 0, "success": 0, "failed": 0}

        name_stats[conn_name]["total"] += 1
        if result["status"] == "SUCCESS":
            name_stats[conn_name]["success"] += 1
        else:
            name_stats[conn_name]["failed"] += 1

    # Timing statistics (only for successful connections)
    successful_results = [
        r for r in test_results if r["status"] == "SUCCESS" and r["total_time"]
    ]
    if successful_results:
        total_times = [r["total_time"] for r in successful_results]
        avg_time = sum(total_times) / len(total_times)
        min_time = min(total_times)
        max_time = max(total_times)
    else:
        avg_time = min_time = max_time = 0

    return {
        "summary": {
            "total_tests": total,
            "success_count": success_count,
            "partial_count": partial_count,
            "failed_count": failed_count,
            "error_count": error_count,
            "success_rate": (success_count / total * 100) if total > 0 else 0,
        },
        "by_connection_type": type_stats,
        "by_connection_name": name_stats,
        "timing": {
            "avg_connection_time": avg_time,
            "min_connection_time": min_time,
            "max_connection_time": max_time,
            "successful_connections": len(successful_results),
        },
    }


def validate_schema(
    schema_type: str, schema_file: str, file_or_dir: str, logger: TestLogger
) -> bool:
    """
    Validate the given data file against the specified schema type.

    Args:
        schema_type: Type of schema to validate against (e.g., "config", "scenario")
        schema_file: Path to the schema file
        data_file: Path to the data file to validate

    Returns:
        bool
    """

    if schema_type not in ["config", "scenario"]:
        logger.error("SCHEMA_TYPE must be 'config' or 'scenario'.")
        return False
    schema_file = (
        schema_file[0]
        if schema_file
        else os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "spec",
            "schema_checker",
            f"{schema_type}_schema.json",
        )
    )
    if not os.path.exists(schema_file):
        logger.error(f"❌ Schema file not found: {schema_file}")
        return
    if not os.path.exists(file_or_dir):
        logger.error(f"❌ File or directory not found: {file_or_dir}")
        return
    if os.path.isdir(file_or_dir):
        matched_files = discover_tests(file_or_dir, None, logger=logger)
        if not matched_files:
            logger.error(f"❌ No matching files found in directory: {file_or_dir}")
            return
    else:
        matched_files = [file_or_dir]
    factory = ExecutorFactory().get_instance(schema_file)
    executor = factory.get_executor(schema_type)
    for file_path in matched_files:
        logger.info(f"Validating {file_path} against {schema_type} schema...")
        if not os.path.exists(file_path):
            logger.error(f"❌ File not found: {file_path}")
            continue
        if not os.path.isfile(file_path):
            logger.error(f"❌ Not a file: {file_path}")
            continue
        if not file_path.endswith((".yaml", ".yml", ".json")):
            logger.error(f"❌ Unsupported file format: {file_path}")
            continue
        executor(schema_file).validate_schema(file_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="YAML-Based Test Executor")

    parser.add_argument(
        "--test_dir", type=str, required=False, help="Path to the root tests directory"
    )
    parser.add_argument(
        "--workspace",
        type=str,
        required=False,
        help="Directory for logs, JSON, and results",
    )
    parser.add_argument("--test_id", type=str, help="Filter by test_id")
    parser.add_argument("--test_name", type=str, help="Filter by test_name")
    parser.add_argument("--test_group", type=str, help="Filter by test_group")
    parser.add_argument("--tags", nargs="+", help="Filter by tags")
    parser.add_argument(
        "--conn_config", "-cc", type=str, help="Path to the connection config file"
    )
    parser.add_argument(
        "--list",
        "-l",
        action="store_true",
        help="List all available tests without running them",
    )
    parser.add_argument(
        "--discover_connections",
        "-dc",
        action="store_true",
        help="List all available connections without running tests",
    )
    parser.add_argument(
        "--list_scenarios_with_connections",
        "-lsc",
        action="store_true",
        help="List all scenarios with connections without running tests",
    )
    parser.add_argument(
        "--list_scenarios",
        "-ls",
        action="store_true",
        help="List all scenarios without running tests",
    )
    parser.add_argument(
        "--run_with_discover_connections",
        "-rdc",
        default=False,
        action="store_true",
        help="Discover and test all connections before running tests",
    )
    parser.add_argument(
        "--schema_check",
        nargs="+",
        help=(
            "Arguments: SCHEMA_TYPE FILE_OR_DIR [SCHEMA_FILE]\n"
            "SCHEMA_TYPE: config or scenario\n"
            "FILE_OR_DIR: Path to file or directory\n"
            "SCHEMA_FILE: Optional path to schema file (uses default if omitted)"
        ),
    )
    parser.add_argument(
        "--run_with_schema_check",
        "-rsc",
        default=False,
        action="store_true",
        help="Run tests with schema check",
    )
    args = parser.parse_args()

    test_dir = args.test_dir or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests"
    )
    if not os.path.exists(test_dir):
        parser.error(f"Test directory does not exist: {test_dir}")

    workspace = args.workspace or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "workspace"
    )
    print("test dir", test_dir)
    if not os.path.exists(workspace):
        os.makedirs(workspace, exist_ok=True)

    log_path = os.path.join(workspace, "logs")
    TestLogger(log_dir=log_path)
    logger = TestLogger().get_logger()
    log_dir = TestLogger().get_log_dir()
    logger.info(f"Log directory: {log_dir}")
    logger.info(f"Starting test discovery in: {test_dir}")

    all_tests_list = discover_tests(test_dir, None, logger=logger)
    logger.info(f"Found {len(all_tests_list)} matching test cases.")
    if all_tests_list:
        if args.list_scenarios or args.list:
            list_tests(all_tests_list, logger=logger)
            return

    if not all_tests_list:
        logger.warning("⚠️ No matching test cases found.")
        return

    # Schema check
    if args.schema_check:
        if len(args.schema_check) < 2:
            parser.error("At least SCHEMA_TYPE and FILE_OR_DIR are required.")
        schema_type, file_or_dir, *schema_file = args.schema_check
        validate_schema(schema_type, schema_file, file_or_dir, logger)
        return

    if args.conn_config:
        if not os.path.exists(args.conn_config):
            logger.error(f"❌ Connection config file not found: {args.conn_config}")
            return
        # Load connection config if needed (not implemented in this snippet)
    conn_config = json.load(open(args.conn_config, "r")) if args.conn_config else {}
    if args.discover_connections:
        logger.info("Discovering and testing all connections...")
        results = discover_and_test_connections(
            conn_config, timeout=30, export_csv=False
        )
        logger.info(f"Discovery results: {results['discovery']}")
        logger.info(f"Test results: {results['test_results']}")
        logger.info(f"Statistics: {results['statistics']}")
        if not args.run_with_discover_connections:
            logger.info(
                "Skipping test execution as --discover_connections was specified."
            )
            return

    factory = ConnectionFactory.get_instance(conn_config)

    matched_files = discover_tests(test_dir, args, logger=logger)
    print(matched_files)
    for file_path in matched_files:
        run_test(file_path, workspace, logger=logger)

    ConnectionFactory().close_all_connections()
    logger.info("All tests executed successfully.")


if __name__ == "__main__":
    main()
