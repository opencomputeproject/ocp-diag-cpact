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

import sys
import argparse
from email.mime import text
import json
import os
import textwrap
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from tabulate import tabulate

from cpact.versions import get_version_info, __version__
from cpact.utils.logger_utils import TestLogger
from cpact.utils.scenario_parser import load_yaml_file
from cpact.utils.path_resolver import resolve_paths_in_yaml
from cpact.result_builder.result_builder import ResultCollector
from cpact.schema_checker.schema_factory import ExecutorFactory
from cpact.core.orchestrator import Orchestrator
from cpact.system_connections.connection_factory import ConnectionFactory
from cpact.system_connections.connection_discovery import ConnectionDiscovery
from cpact.utils.custom_exception_handler import CustomExceptionHandler

# import sys

# # detect terminal vs file
# ENABLE_COLOR = sys.stdout.isatty()

# try:
#     from colorama import Fore, Style, init

#     init(autoreset=True)
# except:
#     ENABLE_COLOR = False

# def color_severity(sev: str) -> str:
#     if not ENABLE_COLOR:
#         return sev

#     sev_upper = str(sev).upper()
#     if sev_upper == "ERROR":
#         return Fore.RED + sev + Style.RESET_ALL
#     elif sev_upper == "WARNING":
#         return Fore.YELLOW + sev + Style.RESET_ALL
#     elif sev_upper == "INFO" or sev_upper == "PASSED" or sev_upper == "SUCCESS":
#         return Fore.CYAN + sev + Style.RESET_ALL
#     return sev

# --------------------------------------------------------------------------------------
# Discovery
# --------------------------------------------------------------------------------------
def discover_tests(
    test_dir: str,
    filters: Optional[argparse.Namespace],
    logger: Optional[TestLogger] = None,
) -> List[str]:
    """
    Discover all supported test files (YAML/YML) recursively and filter by test metadata.

    Args:
        test_dir: Root directory containing test scenarios.
        filters: Parsed argparse namespace with optional fields:
                 test_id (List[str]), test_name (str), test_group (str), tags (List[str]).
                 If None, no filtering is applied.
        logger: Logger instance.

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
                continue

    return matched_tests


# --------------------------------------------------------------------------------------
# Execution
# --------------------------------------------------------------------------------------
def run_test(
    file_path: str,
    workspace: str,
    logger: Optional[TestLogger] = None,
    historical_data: Optional[List[str]] = None,
) -> None:
    """
    Run a single test scenario from the given file path.

    Args:
        file_path: Path to the test scenario file.
        workspace: Directory for logs and results.
        logger: Logger instance.
        historical_data: Optional list of historical result files for aggregated output.

    Returns:
        None
    """
    logger = logger or TestLogger().get_logger()
    logger.info(f"\n🚀 Running Test: {file_path}")

    scenario_doc = load_yaml_file(file_path)
    if not scenario_doc or "test_scenario" not in scenario_doc:
        logger.error(f"❌ Invalid test scenario in {file_path}. Skipping.")
        return

    start_time = time.time()

    scenario_data = scenario_doc["test_scenario"]
    scenario_data, _ = resolve_paths_in_yaml(
        scenario_data, scenario_data.get("paths", {})
    )

    orchestrator = Orchestrator()
    orchestrator.run(scenario_data, file_path)

    elapsed_time = time.time() - start_time
    logger.info(f"✅ Test completed in {elapsed_time:.2f} seconds")
    logger.info("---------------------- Test Summary -------------------------")

    # Cache singleton instances to avoid repeated lookups
    test_logger = TestLogger()
    log_dir = test_logger.get_log_dir()
    rc = ResultCollector().get_instance()

    rc.print_summary()
    rc.dump_results(os.path.join(log_dir, "test_results.json"))
    # rc.dump_diagnostics(os.path.join(log_dir, "diagnostics_codes.json"))

    # Historical merging & standardized output
    filtered_current = rc.filter_historical_data(
        historical_data or [], rc.scenario_output
    )
    rc.dump_custom_scenario_output(
        os.path.join(log_dir, "scenario_results.json"), filtered_current
    )
    standardized = rc.filter_map_file(filtered_current)
    rc.dump_custom_scenario_output(
        os.path.join(log_dir, "standardized_results.json"), standardized
    )
    rc.dump_diagnostics(
        os.path.join(log_dir, "diagnostics_result_codes.json"), standardized
    )
    rc.print_summary_table()
    logger.info(f"⏱️ Total execution time: {elapsed_time:.2f}s\n")


# --------------------------------------------------------------------------------------
# Listing
# --------------------------------------------------------------------------------------
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


# --------------------------------------------------------------------------------------
# Connection discovery & stats
# --------------------------------------------------------------------------------------
def discover_and_test_connections(
    config: Dict[str, Any], timeout: int = 10, export_csv: bool = False
) -> Dict[str, Any]:
    """
    Discover and test all connections from config.

    Args:
        config: Connection configuration.
        timeout: Timeout for connection tests in seconds.
        export_csv: Whether to export results to CSV.

    Returns:
        Dict containing discovery info, test results, and statistics.
    """
    print("🔍 DISCOVERING ALL POSSIBLE CONNECTIONS...")

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

    # Print results table (keep behavior)
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
    """
    Calculate detailed statistics from test results.

    Args:
        test_results: List of connection test result dicts containing at least
                      'status', 'connection_type', 'connection_name', and optionally 'total_time'.

    Returns:
        Dictionary with summary counts, breakdowns by type and name, and timing aggregates.
    """
    if not test_results:
        return {}

    total = len(test_results)
    success_count = sum(1 for r in test_results if r.get("status") == "SUCCESS")
    partial_count = sum(1 for r in test_results if r.get("status") == "PARTIAL")
    failed_count = sum(1 for r in test_results if r.get("status") == "FAILED")
    error_count = sum(1 for r in test_results if r.get("status") == "ERROR")

    # Stats by connection type
    type_stats: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {"total": 0, "success": 0, "failed": 0}
    )
    for r in test_results:
        t = r.get("connection_type", "UNKNOWN")
        type_stats[t]["total"] += 1
        if r.get("status") == "SUCCESS":
            type_stats[t]["success"] += 1
        else:
            type_stats[t]["failed"] += 1

    # Stats by connection name
    name_stats: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {"total": 0, "success": 0, "failed": 0}
    )
    for r in test_results:
        n = r.get("connection_name", "UNKNOWN")
        name_stats[n]["total"] += 1
        if r.get("status") == "SUCCESS":
            name_stats[n]["success"] += 1
        else:
            name_stats[n]["failed"] += 1

    # Timing stats for successful results with numeric total_time
    successful_times = [
        float(r["total_time"])
        for r in test_results
        if r.get("status") == "SUCCESS"
        and isinstance(r.get("total_time"), (int, float))
    ]
    if successful_times:
        avg_time = sum(successful_times) / len(successful_times)
        min_time = min(successful_times)
        max_time = max(successful_times)
    else:
        avg_time = min_time = max_time = 0.0

    return {
        "summary": {
            "total_tests": total,
            "success_count": success_count,
            "partial_count": partial_count,
            "failed_count": failed_count,
            "error_count": error_count,
            "success_rate": (success_count / total * 100.0) if total > 0 else 0.0,
        },
        "by_connection_type": dict(type_stats),
        "by_connection_name": dict(name_stats),
        "timing": {
            "avg_connection_time": avg_time,
            "min_connection_time": min_time,
            "max_connection_time": max_time,
            "successful_connections": len(successful_times),
        },
    }


# --------------------------------------------------------------------------------------
# Schema validation
# --------------------------------------------------------------------------------------


def get_versioned_schema_dir(schema_type: str, schema_version: str) -> str:
    """
    Get the default schema file path based on schema type and current version.

    Args:
        schema_type: 'config' or 'scenario'.
    Returns:
        Path to the schema file.
    """

    schema_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "spec", "schema"
    )
    schema_dirs = os.listdir(schema_dir)
    if schema_version and schema_version in schema_dirs:
        return os.path.join(schema_dir, schema_version)
    latest_schema_version = sorted(schema_dirs)[-1]

    return os.path.join(
        schema_dir,
        latest_schema_version,
    )


def get_schema_file_path(
    schema_dir: str,
    schema_type: str,
) -> str:
    """
    Resolve the schema file path based on input or default.

    Args:
        schema_type: 'config' or 'scenario'.
        schema_file: Optional list with 0 or 1 element for an explicit schema path.
        schema_version: Version string from the data file.
    Returns:
        Path to the schema file.
    """
    return os.path.join(schema_dir, f"{schema_type}_recipe_schema.json")


def validate_schema(
    schema_type: str,
    schema_file: Optional[List[str]],
    file_or_dir: str,
    logger: Optional[TestLogger],
) -> bool:
    """
    Validate the given data file(s) against the specified schema type.

    Args:
        schema_type: 'config' or 'scenario'.
        schema_file: Optional list with 0 or 1 element for an explicit schema path.
        file_or_dir: Path to a file or a directory to validate.
        logger: Logger instance.

    Returns:
        True if all validations pass; False otherwise.
    """
    logger = logger or TestLogger().get_logger()

    if schema_type not in {"config", "scenario"}:
        logger.error("SCHEMA_TYPE must be 'config' or 'scenario'.")
        return False

    # Resolve schema file: use provided or default path based on __version__

    if not os.path.exists(file_or_dir):
        logger.error(f"❌ File or directory not found: {file_or_dir}")
        return False

    # Collect matching files to validate
    if os.path.isdir(file_or_dir):
        matched_files = discover_tests(file_or_dir, None, logger=logger)
        if not matched_files:
            logger.error(f"❌ No matching files found in directory: {file_or_dir}")
            return False
    else:
        matched_files = [file_or_dir]

    results: List[bool] = []
    report: List[Dict[str, str]] = []
    for fp in matched_files:
        if not os.path.isfile(fp):
            logger.error(f"❌ Not a file: {fp}")
            results.append(False)
            continue
        if not fp.endswith((".yaml", ".yml", ".json")):
            logger.error(f"❌ Unsupported file format: {fp}")
            results.append(False)
            continue
        try:
            fp_data = load_yaml_file(fp)
            if not fp_data:
                logger.error(f"❌ Failed to load data from {fp}.")
                results.append(False)
                continue
            schema_version = fp_data.get("test_scenario", {}).get("schema_version")
            logger.info(
                f"Using schema version: {schema_version or '-latest-'} for {fp}"
            )
            schema_dir = get_versioned_schema_dir(schema_type, schema_version)
            logger.info(f"Using schema directory: {schema_dir} for {fp}")
            resolved_schema_file = (
                schema_file[0]
                if schema_file
                else get_schema_file_path(schema_dir, schema_type)
            )
            logger.info(f"Using schema file: {resolved_schema_file} for {fp}")
            if not os.path.exists(resolved_schema_file):
                logger.error(f"❌ Schema file not found: {resolved_schema_file}")
                return False
            logger.info(f"Validating {fp} against {schema_type} schema...")
            factory = ExecutorFactory().get_instance(resolved_schema_file)
            executor = factory.get_executor(schema_type)
            schema_executor = executor(resolved_schema_file, schema_dir)
            res = schema_executor.validate_schema(fp)
            report.append(
                ResultCollector.get_instance().get_schema_validation_results()
            )
            ResultCollector.get_instance().reset_schema_validation_results()
            results.append(bool(res))
        except Exception as exc:
            CustomExceptionHandler.print_exception(exc)
            logger.error(f"❌ Validation error for {fp}: {exc}")
            results.append(False)

    print_validation_report(report, logger)
    ResultCollector.get_instance().generate_schema_report(
        report,
        os.path.join(
            TestLogger().get_log_dir(), f"{schema_type}_schema_validation_report"
        ),
        output_type="json",
    )
    return all(results)


def print_validation_report(report: List[Dict[str, str]], logger: TestLogger) -> None:
    """
    Print a formatted validation report to console and log file.
    This function takes a list of validation report sections and displays them in a
    formatted table with color-coded severity levels. The report is printed to both
    the console logger and saved to a text file in the log directory.
    Args:
        report (List[Dict[str, str]]): A list of report sections, where each section
            contains multiple rows. Each row is a dictionary with keys like "Category",
            "Colateral", "Status", "Message", "Path", and "Line".
        logger (TestLogger): The logger instance used to output the formatted report
            and manage log file paths.
    Returns:
        None
    Behavior:
        - Attempts to import colorama for colored output. Falls back to plain text if unavailable.
        - Wraps text in cells to 30 characters width for readability.
        - Color-codes severity levels: ERROR (red), WARNING (yellow), INFO/PASSED (cyan).
        - Groups report sections with visual breaks.
        - Displays the table using tabulate in grid format.
        - Saves the report (without colors) to "schema_validation_report.txt" in the log directory.
        - Prints "No issues found." if the report is empty.
    Raises:
        None (gracefully handles missing colorama dependency)
    """

    def wrap_text(text, width=30):
        if text is None:
            return ""
        return "\n".join(textwrap.wrap(str(text), width))

    if not report:
        print("No issues found.")
        return

    all_rows = []
    group_breaks = []

    for section in report:
        first = True
        for row in section:
            r = row.copy()
            for k in r:
                r[k] = wrap_text(r[k], 30)
            if "Status" in r:
                r["Status"] = ResultCollector.get_instance().color_severity(r["Status"])
            if not first:
                if "Category" in r:
                    r["Category"] = ""
                if "Colateral" in r:
                    r["Colateral"] = ""
            first = False
            all_rows.append(r)
        group_breaks.append(len(all_rows))
    table_lines = tabulate(all_rows, headers="keys", tablefmt="grid")


    logger.info(
        f"""
================================================================
                    VALIDATION REPORT
================================================================
{table_lines}
================================================================
                """
    )
    
    log_path = os.path.join(TestLogger().get_log_dir(), "schema_validation_report.txt")
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("VALIDATION REPORT\n")
        f.write("=" * 80 + "\n")
        f.write(ResultCollector().clean_ansi(table_lines))
        f.write("\n" + "=" * 80 + "\n")


def get_final_results() -> bool:
    rc = ResultCollector().get_instance()
    step_results = rc.get_step_results()

    return not any(
        step.get("status") in {"FAIL", "fail", "error", "ERROR"}
        for step in step_results
    )

# --------------------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------------------
def main() -> None:
    print("=" * 80)
    print(get_version_info())
    print("=" * 80)
    print("Starting framework initialization...\n")

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
    parser.add_argument("--test_id", nargs="+", help="Filter by test_id")
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
        dest="run_with_schema_check",
        action="store_true",
        help="Enable schema check",
    )
    parser.add_argument(
        "--no-schema-check",
        dest="run_with_schema_check",
        action="store_false",
        help="Disable schema check",
    )
    parser.add_argument(
        "--historical_data",
        nargs="+",
        help="List of previously ran output files for calculating result.",
    )
    parser.add_argument(
        "--run_all_scenarios",
        "-ras",
        action="store_true",
        help="Run all scenarios without filtering",
    )
    parser.set_defaults(run_with_schema_check=True)
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

    # Initialize logger and log paths
    log_path = os.path.join(workspace, "logs")
    TestLogger(log_dir=log_path)
    logger = TestLogger().get_logger()
    log_dir = TestLogger().get_log_dir()
    logger.info(f"Log directory: {log_dir}")
    logger.info(f"Starting test discovery in: {test_dir}")

    # Initial discovery (no filters) for listing-only flows
    if (args.test_group or args.test_id or args.test_name or args.tags) and (args.list_scenarios or args.list):
        logger.info(
            "Note: --list will show all discovered tests without applying filters."
        )
        all_tests_list = discover_tests(test_dir, args, logger=logger)
        if not all_tests_list:
            logger.warning("⚠️ No matching test cases found.")
            return
        list_tests(all_tests_list, logger=logger)
        logger.info(f"Found {len(all_tests_list)} matching test cases.")
        return
    elif args.list_scenarios or args.list:
        all_tests_list = discover_tests(test_dir, None, logger=logger)
        if not all_tests_list:
            logger.warning("⚠️ No matching test cases found.")
            return
        logger.info(f"Found {len(all_tests_list)} matching test cases.")
        list_tests(all_tests_list, logger=logger)
        return


    # Schema check mode (explicit)
    if args.schema_check:
        if len(args.schema_check) < 2:
            parser.error("At least SCHEMA_TYPE and FILE_OR_DIR are required.")
        schema_type, file_or_dir, *schema_file = args.schema_check
        validate_schema(schema_type, schema_file, file_or_dir, logger)
        return

    # Load connection config if provided
    conn_config: Dict[str, Any] = {}
    if args.conn_config:
        if not os.path.exists(args.conn_config):
            logger.error(f"❌ Test result: FAIL, Connection config file not found: {args.conn_config}")
            return
        with open(args.conn_config, "r", encoding="utf-8") as cf:
            conn_config = json.load(cf)

    # Optional: discover/test connections
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

    # Prepare connection factory for execution phase
    factory = ConnectionFactory.get_instance(conn_config)
    if args.run_all_scenarios:
        logger.info("Running all scenarios without filtering.")
        matched_files = discover_tests(test_dir, None, logger=logger)
    else:
        matched_files = discover_tests(test_dir, args, logger=logger)

    if args.run_with_schema_check:
        for matched_file in matched_files:
            ok = validate_schema(
                schema_type="scenario",
                schema_file=None,
                file_or_dir=matched_file,
                logger=logger,
            )
            if not ok:
                logger.error(f"❌ Recipe Schema Check Failed!!! for {matched_file}")
                factory.close_all_connections()
                logger.error("❌ Final Test Result: FAIL")
                sys.exit(1)

    print("Matched Files are: ", matched_files)
    for file_path in matched_files:
        print("Runnig File: ", file_path)
        run_test(
            file_path=file_path,
            workspace=workspace,
            logger=logger,
            historical_data=args.historical_data,
        )

    factory.close_all_connections()
    logger.info("All tests executed successfully.")
    result = get_final_results()
    logger.info(f"Final Test Result: {'PASS' if result else 'FAIL'}")
    import logging
    if not result:
        logging.shutdown()
        sys.exit(1)
    logging.shutdown()

if __name__ == "__main__":
    main()
    import sys

    sys.exit(0)
