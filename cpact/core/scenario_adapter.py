from __future__ import annotations

from typing import Any, Dict, List, Optional


class ScenarioAdapter:
    """Version-aware access to scenario fields needed for selection and launch."""

    def __init__(self, scenario_dict: Dict[str, Any]):
        self.scenario = scenario_dict or {}
        self.schema_version = self._detect_schema_version()

    def _detect_schema_version(self) -> str:
        if "schema_version" in self.scenario:
            return str(self.scenario["schema_version"])
        if "recipe_metadata" in self.scenario:
            metadata = self.scenario.get("recipe_metadata", {})
            return str(metadata.get("schema_version", "0.9"))
        return "0.8"

    def get_schema_version(self) -> str:
        return self.schema_version

    def get_test_id(self) -> Optional[str]:
        if self.schema_version == "0.8":
            return self.scenario.get("test_id")
        return None

    def get_recipe_id(self) -> Optional[str]:
        if self.schema_version == "0.9":
            return self.get_recipe_metadata().get("recipe_id")
        return None

    def get_primary_id(self) -> Optional[str]:
        return self.get_recipe_id() if self.schema_version == "0.9" else self.get_test_id()

    def get_test_name(self) -> str:
        return self.scenario.get("test_name", "")

    def get_test_group(self) -> str:
        return self.scenario.get("test_group", "")

    def get_test_description(self) -> str:
        return self.scenario.get("test_description") or self.scenario.get("description", "")

    def get_paths(self) -> Dict[str, Any]:
        return self.scenario.get("paths", {})

    def get_tags(self) -> List[str]:
        return self.scenario.get("tags", []) or []

    def get_test_steps(self) -> List[Dict[str, Any]]:
        return self.scenario.get("test_steps", []) or []

    def get_recipe_metadata(self) -> Dict[str, Any]:
        if self.schema_version == "0.9":
            return self.scenario.get("recipe_metadata", {}) or {}
        return {}

    def get_supplier_id(self) -> Optional[str]:
        return self.get_recipe_metadata().get("supplier_id")

    def get_platform_id(self) -> Optional[str]:
        return self.get_recipe_metadata().get("platform_id")

    def get_property(self, property_name: str) -> Any:
        if property_name == "schema_version":
            return self.get_schema_version()
        if property_name == "test_id":
            return self.get_test_id()
        if property_name == "recipe_id":
            return self.get_recipe_id()
        if property_name == "primary_id":
            return self.get_primary_id()
        if property_name == "test_name":
            return self.get_test_name()
        if property_name == "test_group":
            return self.get_test_group()
        if property_name == "tags":
            return self.get_tags()
        if self.schema_version == "0.9":
            return self.get_recipe_metadata().get(property_name)
        return self.scenario.get(property_name)

    def get_launchable_steps(self) -> List[Dict[str, Any]]:
        return [
            step for step in self.get_test_steps()
            if step.get("step_type") == "command_execution"
        ]

    def get_step_execution_spec(self, step_id: str) -> Optional[Dict[str, Any]]:
        for step in self.get_test_steps():
            if step.get("step_id") != step_id:
                continue
            return {
                "step_id": step.get("step_id"),
                "step_name": step.get("step_name"),
                "step_type": step.get("step_type"),
                "connection_type": step.get("connection_type"),
                "connection": step.get("connection"),
                "container_name": step.get("container_name"),
                "step_command": step.get("step_command"),
                "use_sudo": step.get("use_sudo", False),
                "method": step.get("method"),
                "headers": step.get("headers"),
                "body": step.get("body"),
                "duration": step.get("duration"),
                "loop": step.get("loop"),
                "validator_type": step.get("validator_type"),
                "entry_criteria": step.get("entry_criteria"),
            }
        return None
