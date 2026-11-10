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
import argparse
import copy
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from tabulate import tabulate

from cpact.core.context import ExecutionContext
from cpact.core.context import Context
from cpact.core.orchestrator import Orchestrator
from cpact.core.recipe_filter import RecipeFilter
from cpact.core.recipe_selector import RecipeSelector
from cpact.core.scenario_adapter import ScenarioAdapter
from cpact.analysis.followup_resolver import FollowUpResolver
from cpact.result_builder.result_builder import ResultCollector
from cpact.scenario_recipe_creator.scenario_creator import main as ScenarioCreator
from cpact.schema_checker import ValidationRequest
from cpact.schema_checker.schema_service import SchemaService
from cpact.scoring.score_manager import ScoreManager
from cpact.scoring.score_result import ScorePrinter
from cpact.system_connections.connection_discovery import ConnectionDiscovery
from cpact.system_connections.connection_factory import ConnectionFactory
from cpact.utils.custom_exception_handler import CustomExceptionHandler
from cpact.utils.logger_utils import TestLogger
from cpact.utils.path_resolver import resolve_paths_in_yaml
from cpact.utils.scenario_parser import load_yaml_file
from cpact.versions import get_version_info, __version__

DEFAULT_MAX_FOLLOWUP_DEPTH = 10

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


def validate_filter_parameters(filters: Optional[argparse.Namespace]) -> None:
    if not filters:
        return
    has_v08 = any(
        [
            getattr(filters, "test_id", None),
            getattr(filters, "test_name", None),
            getattr(filters, "test_group", None),
            getattr(filters, "tags", None),
        ]
    )
    has_v09 = bool(getattr(filters, "recipe_filters", None))
    if has_v08 and has_v09:
        raise ValueError(
            "Cannot combine 0.8-style filters (--test_id, --test_name, --test_group, --tags) "
            "with 0.9-style filters (--recipe-filter)."
        )


def discover_scenarios(
    test_dir: str,
    filters: Optional[argparse.Namespace],
    logger: Optional[TestLogger] = None,
) -> List[Tuple[str, ScenarioAdapter]]:
    logger = logger or TestLogger().get_logger()
    validate_filter_parameters(filters)
    matched_scenarios: List[Tuple[str, ScenarioAdapter]] = []

    recipe_filter: Optional[RecipeFilter] = None
    recipe_filter_specs = getattr(
        filters, "recipe_filters", None) if filters else None
    if recipe_filter_specs:
        recipe_filter = RecipeFilter()
        for filter_spec in recipe_filter_specs:
            recipe_filter.add_filter(filter_spec)

    for root, _, files in os.walk(test_dir):
        for file in files:
            if not file.endswith((".yaml", ".yml", ".json")):
                continue

            file_path = os.path.join(root, file)
            try:
                data = load_yaml_file(file_path)
                metadata = data.get("test_scenario", {})
                adapter = ScenarioAdapter(metadata)

                if filters:
                    if getattr(filters, "test_id", None):
                        if adapter.get_test_id() not in filters.test_id:
                            continue
                    if getattr(filters, "test_name", None):
                        name = adapter.get_test_name()
                        if filters.test_name.lower() not in name.lower():
                            continue
                    if getattr(filters, "test_group", None):
                        if filters.test_group != adapter.get_test_group():
                            continue
                    if getattr(filters, "tags", None):
                        scenario_tags = set(adapter.get_tags())
                        if not scenario_tags.intersection(set(filters.tags)):
                            continue
                    if recipe_filter and not recipe_filter.matches(adapter):
                        continue

                matched_scenarios.append((file_path, adapter))
            except Exception as exc:
                CustomExceptionHandler.print_exception(exc)
                logger.error(f"Failed to parse {file_path}: {exc}")
                continue

    return matched_scenarios


def discover_tests(
    test_dir: str,
    filters: Optional[argparse.Namespace],
    logger: Optional[TestLogger] = None,
) -> List[str]:
    """
    Discover all supported scenario files (YAML/YML/JSON) recursively and filter by test metadata.

    Args:
        test_dir: Root directory containing test scenarios.
        filters: Parsed argparse namespace with optional fields:
                 test_id (List[str]), test_name (str), test_group (str), tags (List[str]).
                 If None, no filtering is applied.
        logger: Logger instance.

    Returns:
        A list of absolute file paths that match the criteria.
    """
    return [file_path for file_path, _ in discover_scenarios(test_dir, filters, logger=logger)]


def _prepare_launchable_scenario(
    file_path: str,
    scenario_data: Dict[str, Any],
    logger: Optional[TestLogger] = None,
) -> Tuple[Dict[str, Any], ScenarioAdapter]:
    logger = logger or TestLogger().get_logger()
    adapter = ScenarioAdapter(scenario_data)
    if adapter.get_schema_version() != "0.9":
        return scenario_data, adapter

    launchable_steps = adapter.get_launchable_steps()
    if not launchable_steps:
        raise ValueError(
            f"Selected v0.9 recipe is not launchable in the current milestone: {file_path}"
        )

    launch_step = launchable_steps[0]
    launch_ready = copy.deepcopy(scenario_data)
    launch_ready["test_id"] = adapter.get_primary_id() or file_path
    launch_ready["test_steps"] = [launch_step]

    logger.info(
        "Selected v0.9 recipe %s; launching first command_execution step %s",
        adapter.get_primary_id(),
        launch_step.get("step_id", "unknown"),
    )
    return launch_ready, ScenarioAdapter(launch_ready)


# --------------------------------------------------------------------------------------
# Execution
# --------------------------------------------------------------------------------------
def run_test(
    file_path: str,
    workspace: str,
    logger: Optional[TestLogger] = None,
    historical_data: Optional[List[str]] = None,
    score_weights_path: Optional[str] = None,
    run_schema_check: bool = True,
) -> List[str]:
    """
    Run a single test scenario from the given file path.

    Args:
        file_path: Path to the test scenario file.
        workspace: Directory for logs and results.
        logger: Logger instance.
        historical_data: Optional list of historical result files for aggregated output.
        score_weights_path: Optional path to the scoring weights configuration.
        run_schema_check: Whether to validate the recipe (and its children) before execution.

    Returns:
        Recipe ids this run asked to be executed as follow-ups.
    """
    logger = logger or TestLogger().get_logger()
    logger.info(f"\n\U0001F680 Running Test: {file_path}")

    scenario_doc = load_yaml_file(file_path)
    if not scenario_doc or "test_scenario" not in scenario_doc:
        logger.error(f"\u274c Invalid test scenario in {file_path}. Skipping.")
        return []

    start_time = time.time()

    scenario_data = scenario_doc["test_scenario"]
    scenario_data, adapter = _prepare_launchable_scenario(
        file_path, scenario_data, logger)
    scenario_data, _ = resolve_paths_in_yaml(
        scenario_data, adapter.get_paths())

    execution_id = adapter.get_primary_id()
    score_manager = ScoreManager(config_path=score_weights_path)
    context = ExecutionContext(logger, score_manager)
    orchestrator = Orchestrator(context)
    score_manager.start_run(execution_id=execution_id,
                            recipe_name=adapter.get_test_name())

    valid = not run_schema_check or validate_recipe(
        schema_type="scenario",
        scenario_path=file_path,
        schema_file=None,
        score_manager=score_manager,
        execution_id=execution_id,
        logger=logger,
    )

    if not valid:
        score_manager.end_run(execution_id=execution_id)
        return []

    orchestrator.run(scenario_data, file_path)

    score_manager.end_run(execution_id=execution_id)

    follow_up_recipe_ids = FollowUpResolver(
        scenario_data, Context.get_instance().get("artifact_manifest")
    ).resolve()

    elapsed_time = time.time() - start_time
    logger.info(f"\u2705 Test completed in {elapsed_time:.2f} seconds")

    if adapter.get_schema_version() == "0.9":
        logger.info(
            "Scoped v0.9 flow complete: CPACT stops after launch orchestration for %s",
            execution_id or file_path,
        )
        return follow_up_recipe_ids

    logger.info("---------------------- Test Summary -------------------------")

    # Cache singleton instances to avoid repeated lookups
    test_logger = TestLogger()
    log_dir = test_logger.get_log_dir()
    rc = ResultCollector().get_instance()

    rc.print_summary()
    rc.dump_results(os.path.join(log_dir, "test_results.json"))

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
    logger.info(f"\u23f1\ufe0f Total execution time: {elapsed_time:.2f}s\n")
    return follow_up_recipe_ids


def build_recipe_index(
    test_dir: str, logger: Optional[TestLogger] = None
) -> Dict[str, str]:
    """Map every discoverable recipe id to its scenario file path."""
    index: Dict[str, str] = {}
    for file_path, adapter in discover_scenarios(test_dir, None, logger=logger):
        recipe_id = adapter.get_primary_id()
        if recipe_id and recipe_id not in index:
            index[recipe_id] = file_path
    return index


def run_test_chain(
    file_path: str,
    workspace: str,
    recipe_index: Dict[str, str],
    logger: Optional[TestLogger] = None,
    historical_data: Optional[List[str]] = None,
    score_weights_path: Optional[str] = None,
    run_schema_check: bool = True,
    max_depth: int = DEFAULT_MAX_FOLLOWUP_DEPTH,
) -> None:
    """
    Run a recipe, then keep running whatever follow-up recipes its OCPTV output
    requests until the chain reports none left.

    A recipe is executed at most once per chain, so a DRC that points back at an
    earlier recipe terminates instead of looping forever.
    """
    logger = logger or TestLogger().get_logger()
    pending: List[Tuple[str, int]] = [(file_path, 0)]
    executed: Set[str] = set()

    while pending:
        current_path, depth = pending.pop(0)
        if current_path in executed:
            logger.info(
                f"Skipping already-executed recipe in this chain: {current_path}")
            continue
        executed.add(current_path)

        follow_up_ids = run_test(
            file_path=current_path,
            workspace=workspace,
            logger=logger,
            historical_data=historical_data,
            score_weights_path=score_weights_path,
            run_schema_check=run_schema_check,
        ) or []

        if not follow_up_ids:
            continue

        if max_depth <= 0:
            logger.info(
                f"Follow-up launching is disabled; not launching {', '.join(follow_up_ids)}."
            )
            continue

        if depth + 1 > max_depth:
            logger.warning(
                f"\u26a0\ufe0f Follow-up depth limit ({max_depth}) reached; not launching "
                f"{', '.join(follow_up_ids)}. Raise --max-followup-depth to continue."
            )
            continue

        for recipe_id in follow_up_ids:
            next_path = recipe_index.get(recipe_id)
            if not next_path:
                logger.error(
                    f"\u274c Follow-up recipe '{recipe_id}' was requested but no recipe "
                    "with that id was discovered in the test directory."
                )
                continue
            if next_path in executed:
                logger.info(
                    f"Follow-up recipe '{recipe_id}' already ran in this chain; stopping that branch."
                )
                continue
            logger.info(
                f"\U0001F501 Queuing follow-up recipe '{recipe_id}' ({next_path}) at depth {depth + 1}"
            )
            pending.append((next_path, depth + 1))


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
        adapter = ScenarioAdapter(test_scenario)
        rows.append(
            [
                str(adapter.get_primary_id() or ""),
                str(adapter.get_test_name()),
                str(adapter.get_test_group()),
                ", ".join([str(tag) for tag in adapter.get_tags()]),
                str(adapter.get_test_description()),
            ]
        )

    if rows:
        logger.info("\n" + tabulate(rows, headers=headers, tablefmt="grid"))

    logger.info("=" * 60)
    if skipped_tests:
        logger.info(f"⚠️ Skipped {len(skipped_tests)} invalid test scenarios:")
        logger.info(
            "\n" + tabulate(skipped_tests,
                            headers=skipped_header, tablefmt="grid")
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

        adapter = ScenarioAdapter(test_scenario)

        conn_details = get_scenario_connection_details(test_scenario)
        rows.append(
            [
                adapter.get_primary_id() or "",
                adapter.get_test_name(),
                adapter.get_test_group(),
                ", ".join([str(t) for t in adapter.get_tags()]),
                adapter.get_test_description(),
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
    success_count = sum(
        1 for r in test_results if r.get("status") == "SUCCESS")
    partial_count = sum(
        1 for r in test_results if r.get("status") == "PARTIAL")
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

def validate_schema(
    schema_type: str,
    schema_file: Optional[List[str]],
    data: str,
    logger: Optional[TestLogger],
):
    """
    Validate the given data file(s) against the specified schema type.

    Args:
        schema_type: 'config' or 'scenario'.
        schema_file: Optional list with 0 or 1 element for an explicit schema path.
        data: Path to the data file to validate.
        logger: Logger instance.

    Returns:
        True if all validations pass; False otherwise.
    """
    service = SchemaService(logger)

    request = ValidationRequest(

        schema_type=schema_type,

        source=data,

        schema_file=schema_file[0]
        if schema_file
        else None,
    )

    return service.validate(request)


def validate_recipe(
    schema_type: str,
    schema_file: Optional[List[str]],
    scenario_path: str,
    logger: TestLogger,
    score_manager,
    execution_id: str,
    visited: Optional[set] = None,
):
    if visited is None:
        visited = set()

    scenario_path = str(Path(scenario_path).resolve())
    # Prevent circular invocation
    scenario_doc = load_yaml_file(scenario_path)
    if not scenario_doc or "test_scenario" not in scenario_doc:
        logger.error(f"Invalid scenario file: {scenario_path}")
        return False

    scenario_data = scenario_doc["test_scenario"]
    scenario_data, _ = resolve_paths_in_yaml(
        scenario_data, scenario_data.get("paths", {})
    )

    if scenario_path in visited:
        logger.warning(f"Circular invocation detected: {scenario_path}")
        return False

    visited.add(scenario_path)

    service = SchemaService(logger)

    request = ValidationRequest(
        schema_type=schema_type,
        source=scenario_path,
        schema_file=schema_file[0] if schema_file else None,
    )

    result = service.validate(request)
    recipe = result.results[0]
    if not recipe.recipe_schema_valid:
        score_manager.record_schema_validation(
            execution_id=execution_id,
            validation_result=recipe,
        )
        return False
    # Record this recipe's validation result
    score_manager.record_schema_validation(
        execution_id=execution_id,
        validation_result=result.results[0],
    )
    # if not result.success:
    #     return False

    child_no = 1

    for step in scenario_data.get("test_steps", []):
        if step.get("step_type") != "invoke_scenario":
            continue

        child_path = step.get("scenario_path")
        if not child_path:
            continue
        scenario_doc = load_yaml_file(child_path)
        if not scenario_doc or "test_scenario" not in scenario_doc:
            logger.error(f"Invalid scenario file: {child_path}")
            return False

        scenario_data = scenario_doc["test_scenario"]
        scenario_data, _ = resolve_paths_in_yaml(
            scenario_data, scenario_data.get("paths", {})
        )
        child_execution_id = f"{execution_id}.{scenario_data.get('test_id', f'child_{child_no}')}"
        score_manager.start_nested_run(
            parent_execution_id=execution_id,
            execution_id=child_execution_id,
            recipe_name=scenario_data.get('test_name'),
        )
        valid = validate_recipe(
            schema_type=schema_type,
            schema_file=schema_file,
            scenario_path=child_path,
            logger=logger,
            score_manager=score_manager,
            execution_id=child_execution_id,
            visited=visited,
        )
        if not valid:
            return False

        child_no += 1

    return True


def get_final_results() -> bool:
    rc = ResultCollector().get_instance()
    step_results = rc.get_step_results()

    return not any(
        step.get("status") in {"FAIL", "fail", "error", "ERROR"}
        for step in step_results
    )


def _fail_if_no_matched_files(
    matched_files: List[str],
    logger: TestLogger,
    factory: ConnectionFactory,
) -> None:
    if matched_files:
        return

    logger.error("❌ No matching scenarios found for execution.")
    factory.close_all_connections()
    logger.error("❌ Final Test Result: FAIL")
    import logging

    logging.shutdown()
    raise SystemExit(1)

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
        "--score_weights", type=str, required=False, help="Path to the score weights file"
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
        "--recipe-filter",
        action="append",
        dest="recipe_filters",
        help="Filter v0.9 recipes by metadata property, e.g. --recipe-filter supplier_id=INTEL",
    )
    parser.add_argument(
        "--list-recipes",
        action="store_true",
        help="List discovered scenarios/recipes with version-aware identifiers",
    )
    parser.add_argument(
        "--show-metadata",
        action="store_true",
        help="Show full recipe metadata when listing recipes",
    )
    parser.add_argument(
        "--recipe-select",
        action="store_true",
        help="Interactively select one discovered scenario/recipe before launch",
    )
    parser.add_argument(
        "--max-followup-depth",
        type=int,
        default=DEFAULT_MAX_FOLLOWUP_DEPTH,
        help=(
            "Maximum follow-up recipe chain depth triggered by DiagnosticIssue "
            "entries requesting FOLLOWUP_RECIPE. Use 0 to disable follow-up launching."
        ),
    )
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
        "--run_scenario_creator",
        "-rsc",
        action="store_true",
        help="Open scenario creator window",
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
    if args.run_scenario_creator:
        ScenarioCreator()
        return
    test_dir = args.test_dir or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests"
    )
    if not os.path.exists(test_dir):
        parser.error(f"Test directory does not exist: {test_dir}")

    workspace = args.workspace or os.path.join(
        os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "workspace"
    )
    score_weights_path = args.score_weights or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))
                        ), "spec", "input", "score_weights.json"
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

    try:
        validate_filter_parameters(args)
    except ValueError as exc:
        parser.error(str(exc))

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

    if args.list_recipes:
        discovered_recipes = discover_scenarios(test_dir, args, logger=logger)
        if not discovered_recipes:
            logger.warning("⚠️ No matching recipes found.")
            return
        RecipeSelector(discovered_recipes).show_list(
            verbose=args.show_metadata)
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
            logger.error(
                f"❌ Test result: FAIL, Connection config file not found: {args.conn_config}")
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
    if args.recipe_select:
        matched_scenarios = discover_scenarios(test_dir, args, logger=logger)
        if not matched_scenarios:
            matched_files = []
        else:
            selected_path, _ = RecipeSelector(
                matched_scenarios).interactive_select()
            matched_files = [selected_path]
    elif args.run_all_scenarios:
        logger.info("Running all scenarios without filtering.")
        matched_files = discover_tests(test_dir, None, logger=logger)
    else:
        matched_files = discover_tests(test_dir, args, logger=logger)

    _fail_if_no_matched_files(matched_files, logger, factory)

    print("Matched Files are: ", matched_files)
    recipe_index = build_recipe_index(test_dir, logger=logger)
    for file_path in matched_files:
        print("Runnig File: ", file_path)
        run_test_chain(
            file_path=file_path,
            workspace=workspace,
            recipe_index=recipe_index,
            logger=logger,
            historical_data=args.historical_data,
            score_weights_path=score_weights_path,
            run_schema_check=args.run_with_schema_check,
            max_depth=args.max_followup_depth,
        )

    ScorePrinter(logger=logger).print_framework_report()

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
