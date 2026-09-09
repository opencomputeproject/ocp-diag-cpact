from __future__ import annotations

from typing import List, Tuple

from cpact.core.scenario_adapter import ScenarioAdapter


class RecipeSelector:
    """Interactive and programmatic selection for discovered scenarios."""

    def __init__(self, recipes: List[Tuple[str, ScenarioAdapter]]):
        self.recipes = recipes

    def show_list(self, verbose: bool = False) -> None:
        print(f"Found {len(self.recipes)} recipes\n")
        for path, adapter in self.recipes:
            if verbose:
                self._show_verbose(path, adapter)
            else:
                self._show_compact(path, adapter)

    def _show_compact(self, path: str, adapter: ScenarioAdapter) -> None:
        print(
            f"  {adapter.get_primary_id() or 'N/A':30} | {adapter.get_test_name():40} | {path}")
        if adapter.get_schema_version() == "0.9":
            metadata = adapter.get_recipe_metadata()
            print(
                f"    Supplier: {metadata.get('supplier_id', ''):15} "
                f"Platform: {metadata.get('platform_id', ''):15} "
                f"Class: {metadata.get('class_code', '')}"
            )

    def _show_verbose(self, path: str, adapter: ScenarioAdapter) -> None:
        print(f"\n{'=' * 80}")
        print(f"Recipe: {adapter.get_primary_id()}")
        print(f"File: {path}")
        print(f"{'=' * 80}")
        print(
            f"  schema_version               : {adapter.get_schema_version()}")
        print(f"  test_name                    : {adapter.get_test_name()}")
        if adapter.get_schema_version() == "0.9":
            for key, value in sorted(adapter.get_recipe_metadata().items()):
                print(f"  {key:30} : {value}")

    def interactive_select(self) -> Tuple[str, ScenarioAdapter]:
        for index, (_, adapter) in enumerate(self.recipes, 1):
            print(
                f"{index}. {adapter.get_primary_id() or 'N/A':20} - {adapter.get_test_name()}")
        while True:
            try:
                choice = int(
                    input(f"\nSelect recipe (1-{len(self.recipes)}): "))
            except ValueError:
                choice = 0
            if 1 <= choice <= len(self.recipes):
                return self.recipes[choice - 1]
            print("Invalid selection. Try again.")
