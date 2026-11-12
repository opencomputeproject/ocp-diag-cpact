"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

===============================================================================
Schema validation entry points for the CPACT CLI: --schema_check and the
pre-run validation of a recipe and every nested recipe it invokes.

Extracted from cpact/main.py; cpact.main re-exports these names.
===============================================================================
"""

from pathlib import Path
from typing import List, Optional

from cpact.schema_checker import ValidationRequest
from cpact.schema_checker.schema_service import SchemaService
from cpact.utils.logger_utils import TestLogger
from cpact.utils.path_guard import PathNotAllowedError, resolve_allowed_path
from cpact.utils.path_resolver import resolve_paths_in_yaml
from cpact.utils.scenario_parser import load_yaml_file


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
        try:
            child_path = resolve_allowed_path(
                child_path, purpose="scenario_path", recipe_path=scenario_path
            )
        except PathNotAllowedError as exc:
            logger.error(str(exc))
            # Record on the parent so the run's final verdict is FAIL.
            score_manager.schema_validation(
                execution_id, passed=False, metadata={"message": str(exc)}
            )
            return False
        scenario_doc = load_yaml_file(child_path)
        if not scenario_doc or "test_scenario" not in scenario_doc:
            logger.error(f"Invalid scenario file: {child_path}")
            score_manager.schema_validation(
                execution_id,
                passed=False,
                metadata={"message": f"Invalid scenario file: {child_path}"},
            )
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
