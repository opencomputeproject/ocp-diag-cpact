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
    - run_test(): Executes a single test scenario and logs results.
    - get_final_results(): Overall PASS/FAIL verdict for the run.
    - main(): Entry point for CLI argument parsing and execution flow.
    - Re-exported from cpact.test_discovery: discover_tests(), list_tests(),
      list_scenarios_with_connections().
    - Re-exported from cpact.connection_checks: discover_and_test_connections(),
      calculate_connection_statistics().
    - Re-exported from cpact.recipe_validation: validate_schema(), validate_recipe().

Usage:
    Run the script with CLI arguments to list, validate, or execute test scenarios.
    Example:
        python test_executor.py --test_dir ./tests --list
        python test_executor.py --schema_check scenario ./tests/specs
        python test_executor.py --discover_connections --conn_config ./config.json
===============================================================================
"""
import os, sys
import argparse
import copy
import json
import time
from typing import Any, Dict, List, Optional

from cpact.scoring.score_manager import ScoreManager
from cpact.scoring.score_result import ScorePrinter
from cpact.versions import get_version_info
from cpact.utils.logger_utils import TestLogger
from cpact.utils.scenario_parser import load_yaml_file
from cpact.utils.path_resolver import resolve_paths_in_yaml
from cpact.result_builder.result_builder import ResultCollector, is_failed_status
from cpact.core.orchestrator import Orchestrator
from cpact.core.context import ExecutionContext
from cpact.system_connections.connection_factory import ConnectionFactory
from cpact.test_discovery import discover_tests, list_tests, list_scenarios_with_connections
from cpact.connection_checks import discover_and_test_connections, calculate_connection_statistics
from cpact.recipe_validation import validate_schema, validate_recipe
from cpact.utils.path_guard import configure_allowed_roots

# Re-exported for callers that import these from cpact.main.
__all__ = [
    "discover_tests",
    "list_tests",
    "list_scenarios_with_connections",
    "discover_and_test_connections",
    "calculate_connection_statistics",
    "validate_schema",
    "validate_recipe",
    "run_test",
    "get_final_results",
    "main",
]

# --------------------------------------------------------------------------------------
# Execution
# --------------------------------------------------------------------------------------
def run_test(
    file_path: str,
    workspace: str,
    logger: Optional[TestLogger] = None,
    historical_data: Optional[List[str]] = None,
    score_weights_path: Optional[str] = None,
    schema_check: bool = True,
) -> None:
    """
    Run a single test scenario from the given file path.

    Args:
        file_path: Path to the test scenario file.
        workspace: Directory for logs and results.
        logger: Logger instance.
        historical_data: Optional list of historical result files for aggregated output.
        score_weights_path: Optional score weights JSON.
        schema_check: Validate the recipe (and nested recipes/map files) before
            running it. False for --no-schema-check.

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
    score_manager = ScoreManager(config_path=score_weights_path)
    context = ExecutionContext(logger, score_manager)

    orchestrator = Orchestrator(context)
    score_manager.start_run(execution_id=scenario_data.get("test_id"),
                            recipe_name=scenario_data.get("test_name"))

    if schema_check:
        valid = validate_recipe(
            schema_type="scenario",
            scenario_path=file_path,
            schema_file=None,
            score_manager=score_manager,
            execution_id=scenario_data.get("test_id"),
            logger=logger,
        )
    else:
        # --no-schema-check: no schema/map events are recorded, so the Schema
        # and Map score categories show as N/A instead of counting against it.
        logger.warning(f"Schema check disabled (--no-schema-check); not validating {file_path}")
        valid = True

    if not valid:
        score_manager.end_run(execution_id=scenario_data.get("test_id"))
        return


    orchestrator.run(scenario_data, file_path)

    score_manager.end_run(execution_id=scenario_data.get("test_id"))

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

    # Historical merging & standardized output. Both filters mutate their input
    # and this block runs after every recipe on the cumulative results, so work
    # on copies; otherwise earlier scenarios get history counts added and map
    # data merged once per later recipe.
    filtered_current = rc.filter_historical_data(
        historical_data or [], copy.deepcopy(rc.scenario_output)
    )
    rc.dump_custom_scenario_output(
        os.path.join(log_dir, "scenario_results.json"), filtered_current
    )
    standardized = rc.filter_map_file(copy.deepcopy(filtered_current))
    rc.dump_custom_scenario_output(
        os.path.join(log_dir, "standardized_results.json"), standardized
    )
    rc.dump_diagnostics(
        os.path.join(log_dir, "diagnostics_result_codes.json"), standardized
    )
    rc.print_summary_table()
    logger.info(f"⏱️ Total execution time: {elapsed_time:.2f}s\n")


def get_final_results() -> bool:
    """Overall verdict for the run.

    False if any step failed, any scenario was reported FAIL (e.g. a failed
    continued step or a scenario with no test_steps), or any recipe failed
    schema validation (such recipes are skipped, so they must not pass).
    """
    rc = ResultCollector().get_instance()
    step_results = rc.get_step_results()

    if any(is_failed_status(step.get("status")) for step in step_results):
        return False

    for scenario in (rc.scenario_output or {}).values():
        if isinstance(scenario, dict) and (scenario.get("results") or {}).get("status") == "FAIL":
            return False

    score_manager = ScoreManager.instance()
    for execution_id in score_manager.all_execution_ids():
        ctx = score_manager.get_context(execution_id)
        if ctx is not None and ctx.schema_exists and not ctx.schema_passed:
            return False
    return True

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
        "--allowed_path",
        action="append",
        default=[],
        metavar="DIR",
        help=(
            "Extra folder that recipe paths (log_analysis_path, expected_output_path, "
            "scenario_path, map_file) may point into. Repeatable. The working directory, "
            "--workspace, --test_dir, the log folder and each recipe's own folder are "
            "always allowed."
        ),
    )
    parser.add_argument(
        "--workspace",
        type=str,
        required=False,
        help="Directory for logs, JSON, and results",
    )
    parser.add_argument(
        "--log_override",
        type=str,
        required=False,
        metavar="LOG_DIR",
        help=(
            "Manual override for the output log folder. Logs and results are written "
            "directly into LOG_DIR (no timestamped test_run_<timestamp> sub-folder). "
            "The folder is reused if it already exists, otherwise it is created."
        ),
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
        try:
            from cpact.scenario_recipe_creator.scenario_creator import main as ScenarioCreator
        except ImportError as exc:
            if "PyQt5" not in str(exc):
                raise
            parser.exit(
                1,
                "The scenario recipe creator GUI needs PyQt5. Install it with:\n"
                "    pip install -r requirements-gui.txt\n",
            )
        ScenarioCreator()
        return
    test_dir = args.test_dir or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests"
    )
    if not os.path.exists(test_dir):
        parser.error(f"Test directory does not exist: {test_dir}")

    workspace = args.workspace or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "workspace"
    )
    score_weights_path = args.score_weights or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "spec", "input", "score_weights.json"
    )
    print("test dir", test_dir)
    if not os.path.exists(workspace):
        os.makedirs(workspace, exist_ok=True)

    # Initialize logger and log paths
    if args.log_override:
        if os.path.exists(args.log_override) and not os.path.isdir(args.log_override):
            parser.error(f"--log_override path exists but is not a directory: {args.log_override}")
        TestLogger(log_dir=args.log_override, use_exact_dir=True)
    else:
        TestLogger(log_dir=os.path.join(workspace, "logs"))
    logger = TestLogger().get_logger()
    log_dir = TestLogger().get_log_dir()
    logger.info(f"Log directory: {log_dir}")
    roots = configure_allowed_roots(
        [os.getcwd(), workspace, test_dir, log_dir, *args.allowed_path]
    )
    logger.info(f"Allowed roots for recipe paths: {roots}")
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
    factory = ConnectionFactory.initialize(conn_config)
    discovery_errors: List[str] = []
    filtered = not args.run_all_scenarios and any(
        [args.test_id, args.test_name, args.test_group, args.tags]
    )
    if args.run_all_scenarios:
        logger.info("Running all scenarios without filtering.")
        matched_files = discover_tests(test_dir, None, logger=logger, errors=discovery_errors)
    else:
        matched_files = discover_tests(test_dir, args, logger=logger, errors=discovery_errors)

    # Nothing executed must not PASS; unparseable recipes fail unfiltered runs
    # (with filters an unparseable file cannot be matched, so it is only logged).
    discovery_ok = True
    if not matched_files:
        logger.error(f"No recipes matched under {test_dir}; nothing was executed.")
        discovery_ok = False
    if discovery_errors:
        message = (
            f"{len(discovery_errors)} recipe file(s) under {test_dir} could not be parsed: "
            + ", ".join(discovery_errors)
        )
        if filtered:
            logger.warning(message)
        else:
            logger.error(message)
            discovery_ok = False

    print("Matched Files are: ", matched_files)
    for file_path in matched_files:
        print("Runnig File: ", file_path)
        run_test(
            file_path=file_path,
            workspace=workspace,
            logger=logger,
            historical_data=args.historical_data,
            score_weights_path=score_weights_path,
            schema_check=args.run_with_schema_check,
        )
    score_result = ScorePrinter(logger=logger)
    score_result.print_framework_report()
    # score_result.print_all_detailed_reports()
    factory.close_all_connections()
    logger.info("Test execution completed.")
    result = get_final_results() and discovery_ok
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
