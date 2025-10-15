"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

===============================================================================
RecipeCreator is a PyQt5-based GUI widget for creating, editing, and exporting test scenario recipes
in JSON or YAML format, based on a provided schema. It supports auto-saving, loading, and validation
of scenario data, including Docker container entries and test steps.
Attributes:
    schema_selected (pyqtSignal): Signal emitted when a schema is selected and loaded.
    scenario_data (dict): Stores the current scenario data.
    scenario_fields (list): List of tuples mapping scenario field keys to their QLineEdit widgets.
    docker_container_list (list): List of Docker container data dictionaries.
    data (dict): Internal representation of the test scenario being edited.
    required (list): List of required fields for the scenario, parsed from the schema.
    schema (dict): The loaded schema for the scenario.
    timer (QTimer): Timer for auto-saving scenario data.

Usage:
    Instantiate RecipeCreator with a schema to launch the scenario recipe editor.
    Use the UI to add/edit scenario info, Docker entries, and test steps.
    Export or auto-save the scenario as needed.
===============================================================================
"""

# ============================ IMPORTS =============================

from __future__ import annotations
import os
import time
import glob
import json
import yaml
import tempfile
from pathlib import Path
from functools import partial
from collections import OrderedDict
from typing import Any, Dict, List, Tuple, Optional

from ruamel.yaml import YAML
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QGroupBox,
    QFileDialog,
    QMessageBox,
    QListWidgetItem,
    QDialog,
    QCheckBox,
    QToolBar,
    QAction,
    QWidgetAction,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtCore import pyqtSignal

from step_widget import StepDialog
from docker_widget import DockerDialog
from schema_order_parser import SchemaOrderParser
from constants import show_error, make_button, APP_ICON, NumberedListWidget, TOOLBAR_QSS

# ============================= CONSTANTS =============================

AUTOSAVE_INTERVAL_MS = 5000  # 5 seconds
AUTOSAVE_KEEP = 5  # keep last 5 autosaves

FILE_FILTER_OPEN: str = (
    "YAML files (*.yaml *.yml);;JSON files (*.json);;All files (*.*)"
)
FILE_FILTER_JSON: str = "JSON files (*.json)"
FILE_FILTER_YAML: str = "YAML files (*.yaml *.yml)"


# ============================= MAIN CLASS =============================
class RecipeCreator(QMainWindow):
    """
    A Qt-based application for creating and editing test scenario recipes.
    This class provides a graphical user interface for defining test scenarios,
    including scenario information, Docker configurations, and test steps.
    It supports loading schemas, creating new recipes, editing existing ones,
    and exporting the data in JSON or YAML format. The application also
    includes autosave functionality to prevent data loss.
    Signals:
        schema_selected (dict): Emitted when a schema is selected or loaded,
                                 passing the schema data as a dictionary.
    Attributes:
        schema (dict): The schema used to define the structure of the recipe data.
        recipe_data (dict): A dictionary holding the current recipe data.
        scenario_fields (list): A list of tuples, where each tuple contains the
                                 key and QLineEdit object for scenario information fields.
        docker_container_list (list): A list of dictionaries, each representing
                                      a Docker container configuration.
        autosave_dir (str): The directory where autosaved files are stored.
        current_autosave_file (str): The path to the current autosave file.
        autosave_timer (QTimer): A QTimer object used for triggering autosave operations.
        autosave_checkbox (QCheckBox): A QCheckBox to enable or disable autosave.
        toolbar (QToolBar): A QToolBar for providing actions like autosave and load autosave.
        docker_list (NumberedListWidget): A NumberedListWidget for displaying and
                                           managing Docker container entries.
        test_list (NumberedListWidget): A NumberedListWidget for displaying and
                                         managing test steps.
        scenario_info_layout (QVBoxLayout): A QVBoxLayout for organizing scenario
                                             information fields.
    Methods:
        __init__(self, schema=None): Initializes the RecipeCreator widget.
        init_ui(self): Initializes the UI components.
        clear_all_fields(self): Clears all input fields and resets the recipe data.
        load_scenario_data(self, scenario_data): Loads and populates scenario data into the widget fields.
        add_docker(self, docker_schema, docker_data=None): Adds a new Docker container entry to the list.
        edit_docker(self, docker_schema=None): Edits an existing Docker container entry.
        remove_docker(self): Removes a Docker container entry from the list.
        add_step(self, step_schema, step_data=None): Adds a new test step to the list.
        edit_step(self, step_schema=None): Edits an existing test step.
        remove_step(self): Removes a test step from the list.
        add_scenario_info_fields(self, scenario_schema, scenario_data=None): Adds input fields for scenario information based on the schema.
        update_scenario_fields(self, scenario_schema, scenario_data={}): Updates the scenario information fields with provided data.
        update_scenario_info(self, key, line_edit): Updates the recipe data with the value from a scenario information field.
        _sanitize(self, obj): Recursively sanitize object to only contain JSON/YAML-serializable items.
        _flatten_once(self, lst): Flattens a list one level if it contains a single list element, or flatten nested lists of dicts into a single list of dicts.
        _normalize_diagnostic(self, diag): Ensure diagnostic_analysis is a list of dicts (flatten nested lists if needed)
        _normalize_output_analysis(self, out): Ensure output_analysis is a list of dicts (similar handling).
        _normalize_entry_criteria(self, ec): Ensure entry_criteria is a list of dicts.
        _normalize_step(self, step): Normalize a step dict.
        collect_all_data_ordered(self): Build and return a fresh OrderedDict containing the test_scenario in a stable order.
        _find_first_nonprimitive(self, obj, path="root"): Debug helper — returns (path, bad_obj, type) for the first non-primitive-like item.
        export_data(self, fmt): Exports the recipe data to a JSON or YAML file.
        export_both(self): optional convenience method to export both with one button press
        get_scenario_data(self): Build a normalized structure and safely dump to the requested format(s).
        toggle_autosave(self, state): Toggles the autosave functionality on or off.
        _perform_autosave(self): Performs the autosave operation.
        update_autosave_menu(self): Updates the autosave menu with the latest autosave files.
        choose_autosave_file(self): Allows the user to choose an autosave file to load.
        load_autosave_file(self, file): Loads data from an autosave file.
        load_scenario(self, scenario_data, fmt): Loads a scenario from a YAML or JSON file.
    """

    schema_selected = pyqtSignal(dict)

    # ----------------------------- Life Cycle Methods -----------------------------
    def __init__(self, schema: Optional[Dict[str, Any]] = None) -> None:
        """
        Initialize the RecipeCreator widget.
        Args:
            schema (dict, optional): A dictionary representing the schema for the
                test scenario. Defaults to None.
        """

        super().__init__()

        # Basic window setup
        self.setWindowTitle("Recipe Creator")  # App title
        self.setWindowIcon(QIcon(APP_ICON))  # App icon
        # disable maximize button
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowMaximizeButtonHint)

        self._yaml = YAML()
        self._yaml.indent(mapping=2, sequence=4, offset=2)
        self._yaml.default_flow_style = False

        # public attributes
        self.schema = schema or {}
        self._recipe_data = {
            "test_scenario": {
                "test_id": "",
                "test_name": "",
                "description": "",
                "group": "",
                "tags": [],
                "docker": [],
                "test_steps": [],
            }
        }

        # protect internal attributes
        self._scenario_data = {}
        self._scenario_fields = []
        self._docker_container_list = []

        self._required = (
            schema.get("properties", {}).get("test_scenario", {}).get("required", [])
            if schema
            else []
        )

        # Auto-save timer setup
        self._autosave_root: Path = Path(tempfile.gettempdir()) / "cpact_autosaves"
        # os.makedirs(self._autosave_dir, exist_ok=True)
        self._autosave_root.mkdir(parents=True, exist_ok=True)
        # Create a new file for this run
        self._current_autosave_file = (
            self._autosave_root / f"autosave_{int(time.time())}.yaml"
        )

        # Timer for autosave
        self._autosave_timer: QTimer = QTimer(self)
        self._autosave_timer.timeout.connect(self._perform_autosave)

        self.create_toolbar()

        self.schema_selected.connect(self._load_scenario_data)  # connect signal
        self._init_ui()

    def _init_ui(self) -> None:
        """
        Initializes the user interface for the Recipe Create Widget.
        This method sets up the main layout and components of the widget, including
        sections for scenario information, Docker images, test steps, and export buttons.
        It dynamically creates and configures the UI elements based on the provided schema
        and scenario data.
        The UI includes:
        - Scenario Information: Fields for entering scenario-specific details.
        - Docker Images: A section to manage Docker entries with options to add, edit, and remove.
        - Test Steps: A section to manage test steps with options to add, edit, and remove.
        - Export Buttons: Buttons to load a scenario, clear fields, and export data in JSON or YAML format.
        Raises:
            ValueError: If no step schema is found in the provided schema.
        Note:
            - The method assumes that `self.schema` and `self.scenario_data` are pre-defined
              and contain the necessary data for generating the UI.
            - The `make_button` function is used to create styled buttons.
            - The `NumberedListWidget` is used for displaying lists of Docker entries and test steps.
        """

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout()
        # Scenario Info
        self._scenario_info_layout = QVBoxLayout()
        scenario_schema = self.schema.get("properties", {}).get("test_scenario", {})
        self._add_scenario_info_fields(scenario_schema)
        layout.addLayout(self._scenario_info_layout)
        # Docker Images
        docker_schema = (
            scenario_schema.get("properties", {}).get("docker", {}).get("items", {})
        )
        docker_properties = docker_schema.get("properties", {})
        self._init_docker_ui(docker_properties, docker_schema, layout)

        # Steps
        step_schema = (
            scenario_schema.get("properties", {}).get("test_steps", {}).get("items", {})
        )
        if not step_schema:
            show_error(self, "No step schema found in the provided schema.")
            return
        step_box = QGroupBox("Test Steps")
        # have 'card' in the objectName so the shadow helper picks it up
        step_box.setObjectName("steps_card")
        step_box.setProperty("card", True)
        step_layout = QVBoxLayout()
        self._test_list = NumberedListWidget()
        s_buttons = QHBoxLayout()
        add_s = make_button("Add Step", "primary", group=step_box)
        add_s.clicked.connect(lambda: self._add_step(step_schema))
        edit_s = make_button("Edit Step", "edit", group=step_box)
        edit_s.clicked.connect(lambda: self._edit_step(step_schema))
        remove_s = make_button("Remove Step", "remove", group=step_box)
        remove_s.clicked.connect(self._remove_step)
        s_buttons.addWidget(add_s)
        s_buttons.addWidget(edit_s)
        s_buttons.addWidget(remove_s)
        step_layout.addWidget(self._test_list)
        step_layout.addLayout(s_buttons)
        step_box.setLayout(step_layout)
        layout.addWidget(step_box)

        # Export Buttons
        # self._add_export_buttons(layout)

        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

    def create_toolbar(self) -> None:
        """
        Creates a toolbar with actions for autosave and loading autosave files.
        This method sets up a QToolBar with a checkbox to enable or disable autosave
        functionality and an action to load autosaved files. The toolbar is added to
        the main window.
        """

        self._toolbar = QToolBar("Main Toolbar")
        self.addToolBar(self._toolbar)
        self._toolbar.setStyleSheet(TOOLBAR_QSS)

        toggle_action = QAction("AutoSave", self)
        toggle_action.setCheckable(True)  # makes it behave like a checkbox
        self._toolbar.addAction(toggle_action)
        toggle_action.toggled.connect(self._toggle_autosave)


        load_autosave_action = QAction(QIcon(), "Load AutoSave", self)
        load_autosave_action.triggered.connect(self._choose_autosave_file)
        self._toolbar.addAction(load_autosave_action)

        export_both_action = QAction(QIcon(), "Export Both", self)
        export_both_action.triggered.connect(self.export_both)
        self._toolbar.addAction(export_both_action)

        export_yaml_action = QAction(QIcon(), "Export YAML", self)
        export_yaml_action.triggered.connect(lambda: self.export_data("yaml"))
        self._toolbar.addAction(export_yaml_action)

        export_json_action = QAction(QIcon(), "Export JSON", self)
        export_json_action.triggered.connect(lambda: self.export_data("json"))
        self._toolbar.addAction(export_json_action)

        clear_all_action = QAction(QIcon(), "Clear All", self)
        clear_all_action.triggered.connect(self._clear_all_fields)
        self._toolbar.addAction(clear_all_action)

        load_recipe_action = QAction(QIcon(), "Load Recipe", self)
        load_recipe_action.triggered.connect(self.load_scenario)
        self._toolbar.addAction(load_recipe_action)

    def _add_export_buttons(self, parent_layout: QVBoxLayout) -> None:
        """
        Adds export buttons to the given layout.
        This method creates a horizontal layout containing buttons for loading a scenario,
        clearing all fields, and exporting data in JSON or YAML formats. The buttons are
        added to the provided layout.
        Args:
            layout (QLayout): The parent layout to which the export buttons layout will be added.
        Buttons:
            - "Load Scenario": Loads a scenario from a YAML file.
            - "Clear": Clears all fields in the form.
            - "Export JSON": Exports the current data to a JSON file.
            - "Export YAML": Exports the current data to a YAML file.
        """

        export_layout = QHBoxLayout()
        load_yaml = make_button("Load Scenario", "primary")
        load_yaml.clicked.connect(partial(self.load_scenario, "yaml"))
        clear_button = make_button("Clear", "remove")
        clear_button.clicked.connect(partial(self._clear_all_fields))
        save_json = make_button("Export JSON", "primary")
        save_json.clicked.connect(partial(self.export_data, "json"))
        save_yaml = make_button("Export YAML", "primary")
        save_yaml.clicked.connect(partial(self.export_data, "yaml"))
        export_layout.addWidget(load_yaml)
        export_layout.addWidget(clear_button)
        export_layout.addWidget(save_json)
        export_layout.addWidget(save_yaml)
        parent_layout.addLayout(export_layout)

    def _init_docker_ui(
        self,
        docker_properties: Optional[dict[str, Any]],
        docker_schema: Optional[dict[str, Any]],
        parent_layout: Optional[QVBoxLayout],
    ) -> None:
        """
        Initializes the Docker UI components within the application.
        This method sets up a user interface section for managing Docker entries.
        It creates a group box containing a numbered list widget and buttons for
        adding, editing, and removing Docker entries. The layout and functionality
        of these components are dynamically configured based on the provided
        Docker properties and schema.
        Args:
            docker_properties (dict): A dictionary containing properties related
                to Docker entries. If None, the UI components will not be initialized.
            docker_schema (dict): A schema defining the structure and validation
                rules for Docker entries. Used when adding or editing entries.
            layout (QLayout, optional): The parent layout to which the Docker UI
                components will be added. Defaults to None.
        Returns:
            None
        """

        if not (parent_layout and docker_properties and docker_schema):
            return

        # Only create Docker section if properties exist
        if docker_properties and docker_schema:
            docker_box = QGroupBox("Docker entries")
            docker_box.setObjectName("steps_card")
            docker_box.setProperty("card", True)
            docker_layout = QVBoxLayout()

            self._docker_list = NumberedListWidget()
            docker_layout.addWidget(self._docker_list)

            btns = QHBoxLayout()
            btn_add = make_button("Add Docker", "primary", group=docker_box)
            btn_add.clicked.connect(lambda: self._add_docker(docker_schema))

            btn_edit = make_button("Edit Docker", "edit", group=docker_box)
            btn_edit.clicked.connect(lambda: self._edit_docker(docker_schema))

            btn_remove = make_button("Remove Docker", "remove", group=docker_box)
            btn_remove.clicked.connect(self._remove_docker)

            btns.addWidget(btn_add)
            btns.addWidget(btn_edit)
            btns.addWidget(btn_remove)
            docker_layout.addLayout(btns)

            docker_box.setLayout(docker_layout)
            parent_layout.addWidget(docker_box)

    def _clear_all_fields(self) -> None:
        """
        Clears all input fields, lists, and resets the recipe data to its default state.
        This method performs the following actions:
        - Iterates through all scenario fields and clears their associated line edit widgets.
        - Clears the docker list and test list.
        - Resets the `recipe_data` dictionary to its default structure, which includes:
            - An empty test scenario with fields for test ID, test name, description, group, tags, docker, and test steps.
        """

        for _, line_edit in self._scenario_fields:
            line_edit.clear()
        self._docker_list.clear()
        self._test_list.clear()
        self._recipe_data = {
            "test_scenario": {
                "test_id": "",
                "test_name": "",
                "description": "",
                "group": "",
                "tags": [],
                "docker": [],
                "test_steps": [],
            }
        }

    def _load_scenario_data(self, scenario_data: Dict[str, Any]) -> None:
        """
        Loads and populates the scenario data into the widget.
        Args:
            scenario_data (dict): A dictionary containing the scenario data to be loaded.
                                  It includes details such as 'test_scenario', 'docker', and 'test_steps'.
        Returns:
            None
        Functionality:
            - Clears all existing fields in the widget.
            - Updates the widget fields based on the provided scenario schema and data.
            - Iterates through the 'docker' configurations in the scenario data and adds them to the widget.
            - Iterates through the 'test_steps' in the scenario data and adds them to the widget.
        """

        self._clear_all_fields()
        self._scenario_data = scenario_data or {}
        scenario_schema = self.schema.get("properties", {}).get("test_scenario", {})
        ts = self._scenario_data.get("test_scenario", {})

        # Update scenario info fields
        self._update_scenario_fields(scenario_schema, ts)

        # Load Docker entries
        docker = ts.get("docker", [])
        for d in docker:
            self._add_docker(
                scenario_schema.get("properties", {})
                .get("docker", {})
                .get("items", {}),
                d,
            )

        # step entries
        # steps = self._scenario_data.get("test_steps", [])
        for s in ts.get("test_steps", []):
            self._add_step(
                scenario_schema.get("properties", {})
                .get("test_steps", {})
                .get("items", {}),
                s,
            )

    def _add_scenario_info_fields(
        self,
        scenario_schema: Dict[str, Any],
        scenario_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Adds input fields for scenario information to the user interface.
        This method dynamically creates and adds input fields (QLineEdit) and their corresponding labels (QLabel)
        to the layout for each property defined in the `scenario_schema`. It also connects the input fields to
        a handler for updating the scenario information.
        Args:
            scenario_schema (Dict[str, Any]): The schema defining the properties of the scenario.
                It should include a "properties" key containing the fields to be added.
            scenario_data (Optional[Dict[str, Any]]): Optional pre-existing data for the scenario.
                This can be used to pre-populate the input fields. Defaults to None.
        Returns:
            None
        """

        fields = scenario_schema.get("properties", {})
        for key in fields.keys():
            if key in ["test_steps", "docker"]:
                continue

            label_text = key.replace("_", " ").capitalize()
            if key in self._required:
                label_text = f"<b>{label_text}</b> <span style='color:red'>*</span>"

            row = QHBoxLayout()
            lbl = QLabel(label_text)

            edit = QLineEdit()
            edit.setPlaceholderText("Enter " + key.replace("_", " ").capitalize())
            edit.textChanged.connect(partial(self._on_scenario_fields_changed, key))

            row.addWidget(lbl)
            row.addWidget(edit)

            self._scenario_fields.append((key, edit))
            self._scenario_info_layout.addLayout(row)

            if scenario_data:
                self._update_scenario_fields(scenario_schema, scenario_data)

    def _update_scenario_fields(
        self, scenario_schema: Dict[str, Any], scenario_data: Dict[str, Any]
    ) -> None:
        """
        Updates the scenario fields in the user interface with the provided scenario data.
        This method iterates through the scenario fields and updates their values based on the
        provided `scenario_data`. For fields with the key "tags", it ensures the tags are
        formatted as a comma-separated string. It also connects the `textChanged` signal of
        each field to the `update_scenario_info` method for real-time updates.
        Args:
            scenario_schema (Dict[str, Any]): The schema defining the structure of the scenario.
                This is currently unused in the method but may be relevant for validation or
                additional processing.
            scenario_data (Dict[str, Any]): A dictionary containing the data to populate the
                scenario fields. Keys in this dictionary correspond to the field names, and
                their values are used to update the fields.
        Returns:
            None
        """

        for key, edit in self._scenario_fields:
            val = scenario_data.get(key, "")
            if key == "tags":
                if isinstance(val, list):
                    text = ", ".join(str(t) for t in val if t.strip())
                    # tags = [t.strip() for t in val if t.strip()]
                elif isinstance(val, str):
                    text = ", ".join(t.strip() for t in val.split(",") if t.strip())
                else:
                    text = ""
                    # tags = [t.strip() for t in val.split(",") if t.strip()]
                # line_edit.setText(", ".join(str(t) for t in tags))
            else:
                text = str(val) if val is not None else ""
            old = edit.blockSignals(True)
            edit.setText(text)
            edit.blockSignals(old)

            self._on_scenario_fields_changed(key, text)
            # edit.textChanged.connect(
            #     partial(self.update_scenario_info, key, edit))
            # edit.blockSignals(old)

    def _on_scenario_fields_changed(self, key: str, text: str) -> None:
        """
        Updates the scenario information in the recipe data when a field changes.
        This method is connected to the textChanged signal of QLineEdit widgets.
        It updates the corresponding key in the `recipe_data` dictionary based on
        the text entered in the line edit. If the key is "tags" or "docker", it
        splits the text by commas and stores it as a list; otherwise, it stores
        the text as a string.
        Args:
            key (str): The key in the `recipe_data` dictionary to be updated.
            line_edit (QLineEdit): The QLineEdit widget that triggered the change.
        """

        if key == "tags":
            tags = [t.strip() for t in text.split(",") if t.strip()]
            self._recipe_data["test_scenario"][key] = tags
        else:
            self._recipe_data["test_scenario"][key] = text

    def _add_docker(
        self,
        docker_schema: Dict[str, Any],
        docker_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Adds a Docker configuration to the list of Docker containers.
        This method opens a dialog for the user to input Docker configuration details.
        If the dialog is accepted and all required fields are provided, the Docker
        configuration is added to the internal list and displayed in the UI.
        Args:
            docker_schema (Dict[str, Any]): The schema defining the structure and
                required fields for the Docker configuration.
            docker_data (Optional[Dict[str, Any]]): Preloaded data for the Docker
                configuration, if any. Defaults to None.
        Returns:
            None
        """

        dialog = DockerDialog(
            self, docker_schema=docker_schema, load_docker_data=docker_data
        )
        required_fields = docker_schema.get("required", [])

        if dialog.exec_() == QDialog.Accepted:
            d = dialog.result()
            if not all(d.get(f) for f in required_fields):
                show_error(self, f'All fields required: {", ".join(required_fields)}')
                return

            name_key = required_fields[0] if required_fields else "container_name"
            title = d.get(name_key, "container_name")
            item = QListWidgetItem(title)
            item.setData(Qt.UserRole, d)
            self._docker_list.addItem(item)
            self._docker_container_list.append(d)

    def _edit_docker(self, docker_schema: Dict[str, Any]) -> None:
        """
        Edits the selected docker entry in the docker list.
        This method allows the user to edit the details of a selected docker entry
        from the docker list. It opens a dialog for editing, validates the input,
        and updates the docker list and internal data structure with the new values.
        Args:
            docker_schema (Optional[Dict[str, Any]]): The schema defining the structure
                of the docker entry, including required fields. If None, defaults are used.
        Functionality:
            - Checks if a docker entry is selected in the list.
            - Displays an error message if no entry is selected.
            - Opens a dialog to edit the selected docker entry.
            - Updates the docker list item text and data with the edited values.
            - Updates the internal `_docker_container_list` with the new data.
        Returns:
            None
        """

        item = self._docker_list.currentItem()
        required_fields = docker_schema.get("required", [])

        if not item:
            show_error(self, "Select a docker entry to edit")
            return

        dlg = DockerDialog(self, item.data(Qt.UserRole), docker_schema=docker_schema)
        if dlg.exec_() == QDialog.Accepted:
            data = dlg.result()
            name_key = required_fields[0] if required_fields else "container_name"
            item.setText(data.get(name_key, "container_name"))
            item.setData(Qt.UserRole, data)
            idx = self._docker_list.row(item)
            self._docker_container_list[idx] = data

    def _remove_docker(self) -> None:
        """
        Removes the selected docker entry from the docker container list and the UI list widget.
        This method retrieves the currently selected item from the docker list widget. If no item
        is selected, it displays an error message prompting the user to select an entry. If an
        item is selected, it removes the corresponding docker entry from the internal container
        list and the UI list widget.
        Args:
            None
        Returns:
            None
        """

        item = self._docker_list.currentItem()
        if not item:
            show_error(self, "Select a docker entry to remove")
            return
        data = item.data(Qt.UserRole)
        try:
            self._docker_container_list.remove(data)
        except ValueError:
            pass
        self._docker_list.takeItem(self._docker_list.row(item))

    def _add_step(
        self, step_schema: Dict[str, Any], step_data: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Adds a new step to the test list based on the provided schema and data.
        This method opens a dialog for the user to input step details, validates the input,
        and adds the step to the test list if all required fields are provided and valid.
        Args:
            step_schema (Dict[str, Any]): The schema defining the structure and required fields
                for the step. It should include a 'required' key with a list of required field names.
            step_data (Optional[Dict[str, Any]]): Preloaded data for the step, if any. Defaults to None.
        Functionality:
            - Opens a dialog for the user to input or edit step details.
            - Validates the input data against the required fields in the schema.
            - Ensures that only one of 'expected_output' or 'expected_output_path' is provided.
            - Displays error messages for invalid or incomplete input.
            - Adds the validated step to the test list with a name derived from the first two required fields.
        Returns:
            None
        """

        dialog = StepDialog(
            self,
            step_schema=step_schema,
            load_step_data=step_data,
            docker_list=self._docker_container_list,
        )
        required_fields = step_schema.get("required", [])
        if dialog.exec_() == QDialog.Accepted:
            d = dialog.result()
            if ("expected_output" in d and "expected_output_path" in d) and (
                d["expected_output"] and d["expected_output_path"]
            ):
                show_error(
                    self,
                    "Only one of expected_output or expected_output_path should be provided.",
                )
                return
            if not all(d.get(f) for f in required_fields):
                show_error(self, f'All fields required: {", ".join(required_fields)}')
                return

            name = f"{d.get('step_id', 'step')} - {d.get('step_name', 'test')}"
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, d)
            self._test_list.addItem(item)

    def _edit_step(self, step_schema: Dict[str, Any]) -> None:
        """
        Edit the selected step in the test list.
        This method allows the user to edit the details of a selected step in the test list.
        It opens a dialog for editing the step's properties based on the provided schema.
        Args:
            step_schema (Dict[str, Any]): A dictionary representing the schema of the step.
                It contains the structure and required fields for the step.
        Functionality:
            - Checks if a step is selected in the test list.
            - Displays an error message if no step is selected.
            - Opens a dialog to edit the selected step's details.
            - Updates the step's name and data in the test list if the dialog is accepted.
        Returns:
            None
        """

        item = self._test_list.currentItem()
        required_fields = step_schema.get("required", [])
        if not item:
            show_error(self, "Select a step to edit")
            return
        d = item.data(Qt.UserRole)
        dlg = StepDialog(
            self, d, step_schema=step_schema, docker_list=self._docker_container_list
        )

        if dlg.exec_() == QDialog.Accepted:
            nd = dlg.result()
            name = f"{nd.get('step_id', 'step')} - {nd.get('step_name', 'name')}"
            item.setText(name)
            item.setData(Qt.UserRole, nd)

    def _remove_step(self) -> None:
        """
        Removes the currently selected step from the test list.
        Arguments:
        None
        Body:
        - Retrieves the currently selected item from the test list.
        - If no item is selected, displays an error message prompting the user to select a step.
        - Removes the selected item from the test list.
        Returns:
        None
        """

        item = self._test_list.currentItem()
        if not item:
            show_error(self, "Select a step to remove")
            return
        self._test_list.takeItem(self._test_list.row(item))

    # ----------------------------- Data Handling Methods -----------------------------

    def __sanitize(self, obj: Any) -> Any:
        """
        Recursively sanitizes an object by ensuring all dictionary keys are strings
        and converting unsupported or unknown object types to strings.
        Args:
            obj (Any): The object to sanitize. It can be of any type, including
                       dictionaries, lists, primitive data types (str, int, float, bool),
                       or None.
        Returns:
            Any: The sanitized object. Dictionaries will have string keys, lists will
                 have sanitized elements, and unsupported or unknown types will be
                 converted to strings. Primitive data types and None are returned as-is.
        Body:
            - If the input is a dictionary, recursively sanitize its keys and values.
            - If the input is a list, recursively sanitize its elements.
            - If the input is a primitive type (str, int, float, bool) or None, return it as-is.
            - For unsupported or unknown types, convert the object to a string.
        """

        if isinstance(obj, dict):
            return {str(k): self.__sanitize(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self.__sanitize(v) for v in obj]
        if isinstance(obj, (str, int, float, bool)) or obj is None:
            return obj
        # fallback: convert unknown objects to string
        return str(obj)

    def _flatten_once(self, lst: Any) -> Any:
        """
        Flattens a single level of nesting in a list.
        This method takes a list that may contain nested lists and flattens it
        by one level, returning a new list with the elements of the nested lists
        extracted and added to the top-level list.
        Args:
            lst (Any): The input to be flattened. If the input is not a list,
                       it is returned as-is.
        Returns:
            Any: A new list with one level of nesting flattened if the input
                 is a list. If the input is not a list, it is returned unchanged.
        """

        if not isinstance(lst, list):
            return lst
        out = []
        for el in lst:
            if isinstance(el, list):
                for sub in el:
                    out.append(sub)
            else:
                out.append(el)
        return out

    def _normalize_diagnostic(self, diag: Any) -> List[Dict[str, Any]]:
        """
        Normalize the diagnostic data into a standardized list of dictionaries.
        This method processes the input diagnostic data, ensuring it is sanitized,
        flattened, and converted into a consistent structure. The resulting structure
        is a list of dictionaries, where each dictionary represents a diagnostic item.
        Args:
            diag (Any): The diagnostic data to normalize. It can be of any type, but
                        typically it is expected to be a dictionary, a list of dictionaries,
                        or a nested list structure.
        Returns:
            List[Dict[str, Any]]: A list of dictionaries representing the normalized
                                  diagnostic data. If the input is None or cannot be
                                  normalized, an empty list is returned.
        Body:
            - If `diag` is None, return an empty list.
            - Sanitize the input using the `_sanitize` method.
            - If `diag` is a dictionary, wrap it in a list and return.
            - If `diag` is a list, flatten it one level and ensure all items are dictionaries.
              - If an item is not a dictionary, convert it to a dictionary with a "value" key.
            - For any other type of input, return an empty list as a fallback.
        """

        if diag is None:
            return []
        # sanitize then flatten
        diag = self.__sanitize(diag)
        # If diag is a dict (old shape), wrap it
        if isinstance(diag, dict):
            return [diag]
        if isinstance(diag, list):
            # flatten nested lists one level, then ensure items are dicts (or convert fallback to dict)
            diag = self._flatten_once(diag)
            norm = []
            for item in diag:
                if isinstance(item, dict):
                    norm.append(item)
                else:
                    # primitive or unexpected structure -> store as {"value": str(item)}
                    norm.append({"value": item})
            return norm
        # else fallback
        return []

    def _normalize_output_analysis(self, out: Any) -> List[Dict[str, Any]]:
        """
        Normalize the output analysis data into a standardized list of dictionaries.
        This method processes the input `out` and ensures that the output is a list of dictionaries,
        regardless of whether the input is a dictionary, a list, or other data types. If the input
        is `None`, an empty list is returned.
        Args:
            out (Any): The input data to be normalized. It can be of any type, including `None`,
                       a dictionary, or a list.
        Returns:
            List[Dict[str, Any]]: A list of dictionaries representing the normalized output.
                                  If the input is a dictionary, it is wrapped in a list.
                                  If the input is a list, its elements are processed to ensure
                                  they are dictionaries. Non-dictionary elements are converted
                                  into dictionaries with a "value" key.
        """

        if out is None:
            return []
        out = self.__sanitize(out)
        if isinstance(out, dict):
            return [out]
        if isinstance(out, list):
            out = self._flatten_once(out)
            norm = []
            for item in out:
                if isinstance(item, dict):
                    norm.append(item)
                else:
                    norm.append({"value": item})
            return norm
        return []

    def _normalize_entry_criteria(self, ec: Any) -> List[Dict[str, Any]]:
        """
        Normalize the input entry criteria into a standardized list of dictionaries.
        This method ensures that the input `ec` is transformed into a list of dictionaries,
        where each dictionary represents an entry criterion. If the input is a single dictionary,
        it is wrapped in a list. If the input is a list, it is flattened and each item is processed
        to ensure it is a dictionary. Non-dictionary items in the list are converted into dictionaries
        with a "value" key.
        Args:
            ec (Any): The input entry criteria, which can be of any type. It is expected to be
                  either None, a dictionary, or a list of dictionaries/values.
        Returns:
            List[Dict[str, Any]]: A list of dictionaries representing the normalized entry criteria.
                      If the input is None, an empty list is returned. If the input is
                      not a dictionary or a list, an empty list is also returned.
        """

        if ec is None:
            return []
        ec = self.__sanitize(ec)
        if isinstance(ec, dict):
            return [ec]
        if isinstance(ec, list):
            ec = self._flatten_once(ec)
            norm = []
            for item in ec:
                if isinstance(item, dict):
                    norm.append(item)
                else:
                    norm.append({"value": item})
            return norm
        return []

    def _normalize_step(self, step: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Normalize a step dictionary by sanitizing its content, applying normalization rules,
        and ensuring compliance with specific step type constraints.
        ### Arguments:
        - `step` (Optional[Dict[str, Any]]):
          A dictionary representing a step, which may contain keys such as `entry_criteria`,
          `step_type`, `output_analysis`, and `diagnostic_analysis`. If `None`, an empty
          dictionary is used.
        ### Body:
        - Sanitizes the input step dictionary to remove invalid or unexpected data.
        - Normalizes the `entry_criteria` field.
        - Normalizes `output_analysis` and `diagnostic_analysis` fields based on the step type.
        - Enforces rules for specific step types:
          - `command_execution`: Excludes `diagnostic_analysis`.
          - `log_analysis`: Excludes `output_analysis`.
          - `invoke_scenario`: Excludes both `diagnostic_analysis` and `output_analysis`.
        - Adds normalized fields back to the step dictionary only if they are allowed
          and non-empty.
        ### Returns:
        - `Dict[str, Any]`:
          A normalized step dictionary with sanitized and validated fields based on the
          step type and normalization rules.
        """

        step = self.__sanitize(step or {})
        # normalize entry criteria always
        step["entry_criteria"] = self._normalize_entry_criteria(
            step.get("entry_criteria", [])
        )

        step_type = (step.get("step_type") or "").strip().lower()

        # Prepare normalized lists (but don't yet force them into step)
        normalized_output = self._normalize_output_analysis(
            step.get("output_analysis", [])
        )
        normalized_diag = self._normalize_diagnostic(
            step.get("diagnostic_analysis", [])
        )

        # Rules:
        # - command_execution: DO NOT add diagnostic_analysis
        # - log_analysis: DO NOT add output_analysis
        # - invoke_scenario: DO NOT add either diagnostic_analysis or output_analysis
        is_command = step_type == "command_execution"
        is_log = step_type == "log_analysis"
        is_invoke = step_type == "invoke_scenario"

        # Remove any disallowed keys if present in raw data
        # (prevents stale or invalid fields from leaking through)
        if is_command and "diagnostic_analysis" in step:
            step.pop("diagnostic_analysis", None)
        if is_log and "output_analysis" in step:
            step.pop("output_analysis", None)
        if is_invoke:
            step.pop("diagnostic_analysis", None)
            step.pop("output_analysis", None)

        # Only add normalized keys when they are allowed AND non-empty
        if not is_log and not is_invoke and normalized_output:
            step["output_analysis"] = normalized_output

        if not is_command and not is_invoke and normalized_diag:
            step["diagnostic_analysis"] = normalized_diag

        return step

    def _collect_all_data_ordered(self) -> OrderedDict:
        """
        Collects and organizes all test scenario data into an ordered dictionary.
        This method gathers data related to a test scenario, including its metadata,
        tags, Docker configurations, and test steps. The data is structured in a
        specific order to ensure consistency and readability.
        Arguments:
            None
        Body:
            - Extracts test scenario metadata such as test_id, test_name,
              description, and test_group from the _recipe_data attribute.
            - Collects tags associated with the test scenario.
            - Iterates through _docker_list to gather Docker-related data, if available.
            - Processes _test_list to normalize and order test steps based on a
              preferred key sequence.
        Returns:
            OrderedDict: A dictionary containing the structured test scenario data
            with the following keys:
            - test_id: The ID of the test scenario.
            - test_name: The name of the test scenario.
            - description: A description of the test scenario.
            - test_group: The group to which the test scenario belongs (if available).
            - tags: A list of tags associated with the test scenario.
            - docker: A list of Docker-related configurations.
            - test_steps: A list of ordered dictionaries representing the test steps.
        """

        scenario = self._recipe_data.get("test_scenario", {})
        ts = OrderedDict()
        ts["test_id"] = scenario.get("test_id", "")
        ts["test_name"] = scenario.get("test_name", "")
        ts["description"] = scenario.get("description", "")
        ts["test_group"] = scenario.get("test_group", "")
        ts["tags"] = scenario.get("tags", []) or []

        # Docker entries
        docker_items: List[Dict[str, Any]] = []
        if hasattr(self, "_docker_list"):
            for i in range(self._docker_list.count()):
                it = self._docker_list.item(i)
                docker_items.append(self.__sanitize(it.data(Qt.UserRole)))
        ts["docker"] = docker_items

        # Steps
        steps: List[OrderedDict] = []
        if hasattr(self, "_test_list"):
            for i in range(self._test_list.count()):
                itm = self._test_list.item(i)
                raw = itm.data(Qt.UserRole) or {}
                norm = self._normalize_step(raw)
                preferred_order = [
                    "step_id",
                    "step_name",
                    "step_description",
                    "entry_criteria",
                    "step_type",
                    "step_command",
                    "log_analysis_path",
                    "scenario_path",
                    "connection",
                    "connection_type",
                    "container_name",
                    "use_sudo",
                    "headers",
                    "loop",
                    "method",
                    "body",
                    "continue",
                    "duration",
                    "validator_type",
                    "expected_output",
                    "expected_output_path",
                    "output_analysis",
                    "diagnostic_analysis",
                ]
                ordered_step = OrderedDict()
                for k in preferred_order:
                    if k in norm:
                        ordered_step[k] = norm.pop(k)
                for k in sorted(norm.keys()):
                    ordered_step[k] = norm[k]
                steps.append(ordered_step)
        ts["test_steps"] = steps

        out = OrderedDict()
        out["test_scenario"] = ts
        return out

    def _find_first_nonprimitive(
        self, obj: Any, path: str = "root"
    ) -> Optional[Tuple[str, Any, type]]:
        """
        Recursively finds the first non-primitive object in a nested structure.
        This method traverses a nested structure (which can include dictionaries,
        ordered dictionaries, lists, and tuples) to locate the first object that
        is not a primitive type. Primitive types are defined as `str`, `int`,
        `float`, `bool`, and `NoneType`.
        Args:
            obj (Any): The object to search through. This can be a primitive,
                       a container (e.g., dict, list, tuple), or a custom object.
            path (str, optional): The string representation of the current path
                                  in the nested structure. Defaults to "root".
        Returns:
            Optional[Tuple[str, Any, type]]: A tuple containing:
                - The path to the first non-primitive object as a string.
                - The first non-primitive object itself.
                - The type of the first non-primitive object.
              Returns `None` if all objects in the structure are primitives.
        """

        primitives = (str, int, float, bool, type(None))
        if isinstance(obj, primitives):
            return None
        if isinstance(obj, (dict, OrderedDict)):
            for k, v in dict(obj).items():
                p = f"{path}['{k}']"
                res = self._find_first_nonprimitive(v, p)
                if res:
                    return res
            return None
        if isinstance(obj, (list, tuple)):
            for idx, v in enumerate(obj):
                p = f"{path}[{idx}]"
                res = self._find_first_nonprimitive(v, p)
                if res:
                    return res
            return None
        # if here, it's not a primitive nor a container
        return (path, obj, type(obj))

    def get_scenario_data(self) -> Tuple[Dict[str, Any], OrderedDict]:
        """
        Retrieves and processes scenario data, ensuring proper ordering, type conversion,
        and cleaning of the data for further use or export.
        Description:
            This method collects scenario data, applies a schema-defined order,
            converts string values to appropriate Python types, and recursively
            cleans the data by removing empty fields. The final data is returned
            as a cleaned dictionary and an ordered dictionary.
        Arguments:
            None
        Body:
            - Collects ordered data using `collect_all_data_ordered`.
            - Applies schema-defined ordering using `SchemaOrderParser`.
            - Converts string values to appropriate Python types (e.g., boolean, integer, float).
            - Recursively cleans the data by removing empty fields and structures.
            - Converts `OrderedDict` to a regular dictionary for JSON/YAML export.
        Returns:
            Tuple[Dict[str, Any], OrderedDict]:
                - A cleaned dictionary (`data`) ready for export.
                - The original ordered dictionary (`data_ordered`) for reference.
        """

        try:
            data_ordered = (
                self._collect_all_data_ordered()
            )  # your existing ordered builder
        except Exception as e:
            QMessageBox.critical(
                self, "Failed to export data", f"Error building data:\n{e}"
            )
            return
        parser = SchemaOrderParser(schema=self.schema)

        # parser.print_extracted_orders()
        root_order = parser.get_order("root")
        ordered_root = parser.order_dict(data_ordered, root_order)
        ordered_root["test_scenario"] = parser.order_test_scenario(
            ordered_root["test_scenario"]
        )

        def convert_type(value: Any) -> Any:
            """Convert string values into proper Python types."""
            if isinstance(value, str):
                val = value.strip()

                # Boolean conversion
                if val.lower() == "true":
                    return True
                if val.lower() == "false":
                    return False

                # Integer conversion
                if val.isdigit():
                    return int(val)

                # Float conversion
                try:
                    return float(val)
                except ValueError:
                    return value  # keep as string if not numeric

            return value

        empties = (
            "",
            None,
            [],
            {},
            "None",
            "null",
            "Null",
            "NULL",
            "none",
            "NA",
            "N/A",
            "n/a",
            "Na",
            "na",
        )

        def clean_data(data: Any) -> Any:
            """Recursively clean empty fields and convert types."""
            if isinstance(data, dict):
                cleaned = {
                    k: clean_data(v) for k, v in data.items() if v not in empties
                }
                return cleaned if cleaned else None  # remove empty dicts
            elif isinstance(data, list):
                cleaned_list = [clean_data(v) for v in data if v not in empties]
                # filter out any None from recursion
                cleaned_list = [v for v in cleaned_list if v is not None]
                return cleaned_list if cleaned_list else None  # remove empty lists
            else:
                return convert_type(data)

        # Convert to regular dict for JSON export

        def to_plain(obj: Any) -> Any:
            if isinstance(obj, OrderedDict):
                return {k: to_plain(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [to_plain(item) for item in obj]
            else:
                return obj

        final_dict = to_plain(ordered_root)
        data = clean_data(final_dict)
        return data, data_ordered

    def export_data(self, fmt: str) -> None:
        """
        Export scenario data to JSON, YAML, or both formats.

        Args:
            fmt (str): Format to export. Accepts 'json', 'yaml', or 'both'.

        Body:
            - Retrieves scenario data using `get_scenario_data()`.
            - Prompts user to select a save location for each format.
            - Validates file extension and writes data to the selected path.
            - Displays success or error messages via QMessageBox.

        Returns:
            None

        """
        data, data_ordered = self.get_scenario_data()
        try:
            if fmt in ("json", "both"):
                path, _ = QFileDialog.getSaveFileName(
                    self, "Save JSON", "", "JSON Files (*.json)"
                )
                if path:
                    if not path.lower().endswith(".json"):
                        path += ".json"
                    with open(path, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=4, ensure_ascii=False)
                    QMessageBox.information(self, "Success", f"JSON exported to {path}")

            if fmt in ("yaml", "both"):
                path, _ = QFileDialog.getSaveFileName(
                    self, "Save YAML", "", "YAML Files (*.yaml *.yml)"
                )
                if path:
                    if not (
                        path.lower().endswith(".yaml") or path.lower().endswith(".yml")
                    ):
                        path += ".yaml"
                    # write sanitized data only
                    with open(path, "w", encoding="utf-8") as f:
                        yaml.dump(data, f)
                    QMessageBox.information(self, "Success", f"YAML exported to {path}")

        except Exception as e:
            # If yaml.safe_dump still raises, try to capture the exact first offending item for debugging
            # and show it in the error dialog.
            bad2 = self._find_first_nonprimitive(data_ordered)
            if bad2:
                path, bad_obj, bad_type = bad2
                QMessageBox.critical(
                    self,
                    "Failed to export data",
                    f"Failed to dump data to {fmt}.\nFirst non-serializable object at {path} (type: {bad_type}).\n\nException:\n{e}",
                )
            else:
                QMessageBox.critical(
                    self, "Failed to export data", f"Failed to dump data:\n{e}"
                )

    # optional convenience method to export both with one button press
    def export_both(self) -> None:
        self.export_data("both")

    def _toggle_autosave(self, state: bool) -> None:
        """
        Toggles the autosave timer based on the checkbox state.
        Args:
            state (int): The state of the checkbox.
                        - 2 indicates the checkbox is checked (enable autosave).
                        - Any other value disables autosave.
        Body:
            - Starts the autosave timer if the checkbox is checked.
            - Stops the autosave timer otherwise.
        Returns:
            None
        """
        if state:  # Checked
            self._autosave_timer.start(AUTOSAVE_INTERVAL_MS)  # every 5 seconds
        else:
            self._autosave_timer.stop()

    def _perform_autosave(self) -> None:
        """
        Performs autosave by writing the current scenario data to a file and maintaining a limited history.
        Description:
            - Retrieves the current scenario data using `get_scenario_data()`.
            - Saves the data to the current autosave file in YAML format.
            - Logs the autosave operation with a timestamp.
            - Maintains only the latest `AUTOSAVE_KEEP` autosave files by deleting older ones.
            - Updates the autosave menu to reflect the latest state.
        Arguments:
            self: Instance of the class containing autosave configuration and methods.
        Body:
            - Calls `get_scenario_data()` to fetch the data to be saved.
            - Writes the data to `self._current_autosave_file` using `yaml.safe_dump`.
            - Prints a confirmation message with timestamp and data.
            - Uses `glob` to find all autosave files and retains only the latest ones.
            - Calls `self._update_autosave_menu()` to refresh the UI or menu state.
        Returns:
            None
        """

        data, stored = self.get_scenario_data()
        with open(self._current_autosave_file, "w") as f:
            yaml.safe_dump(data, f, indent=4)

        # Keep only 5 latest run files
        files = sorted(
            glob.glob(os.path.join(self._autosave_root, "autosave_*.yaml")),
            key=os.path.getmtime,
            reverse=True,
        )
        for old_file in files[AUTOSAVE_KEEP:]:
            os.remove(old_file)

        self._update_autosave_menu()

    def _update_autosave_menu(self) -> None:
        """
        Updates the autosave menu with available autosave files.
        Description:
            - Scans the autosave directory for files matching the pattern 'autosave_*.yaml'.
            - If no autosave files are found, adds a disabled menu item indicating that.
            - Otherwise, adds each autosave file as a selectable menu item.
            - Each menu item is connected to a handler that loads the corresponding autosave file.
        Arguments:
            self: The instance of the class containing autosave configuration and menu references.
        Body:
            - Uses `glob` to find autosave files and sorts them by modification time (newest first).
            - Creates a `QAction` for each file and connects it to `_load_autosave_file`.
            - Handles the case where no autosave files are present by adding a disabled placeholder action.
        Returns:
            None
        """

        files = sorted(
            glob.glob(os.path.join(self._autosave_root, "autosave_*.yaml")),
            key=os.path.getmtime,
            reverse=True,
        )

        if not files:
            no_action = QAction("No AutoSave Found", self)
            no_action.setEnabled(False)
            return

        for file in files:
            label = os.path.basename(file)
            action = QAction(label, self)
            action.triggered.connect(
                lambda checked, f=file: self._load_autosave_file(f)
            )

    def _choose_autosave_file(self) -> None:
        """
        Prompts the user to select an autosave file from available options.
        Description:
            - Scans the autosave directory for files matching the pattern 'autosave_*.yaml'.
            - If no autosave files are found, displays a warning message.
            - If files are found, presents a dialog for the user to choose one.
            - Loads the selected file using `_load_autosave_file`.
        Arguments:
            self: The instance of the class containing autosave configuration and file loading logic.
        Body:
            - Uses `glob` to find autosave files and sorts them by modification time (newest first).
            - Uses `QInputDialog.getItem` to present a selection dialog.
            - If the user confirms a selection, loads the corresponding file.
        Returns:
            None
        """

        files = sorted(
            glob.glob(os.path.join(self._autosave_root, "autosave_*.yaml")),
            key=os.path.getmtime,
            reverse=True,
        )
        if not files:
            QMessageBox.warning(self, "Load AutoSave", "No autosave files found!")
            return

        items = [os.path.basename(f) for f in files]
        file, ok = QInputDialog.getItem(
            self, "Select AutoSave", "Choose a file:", items, 0, False
        )
        if ok and file:
            self._load_autosave_file(os.path.join(self._autosave_root, file))

    def _load_autosave_file(self, file: str) -> None:
        """
        Loads autosave data from the specified file and emits it to the schema handler.
        Description:
            - Opens and reads the YAML-formatted autosave file.
            - Validates the presence and structure of the 'test_scenario' data.
            - Emits the data to the connected schema handler if valid.
            - Displays appropriate message dialogs for success or failure.
        Arguments:
            file (str): Full path to the autosave file to be loaded.
        Body:
            - Uses `yaml.safe_load` to parse the file contents.
            - Checks for required keys and structure in the loaded data.
            - Emits `self.schema_selected` signal with the data if valid.
            - Shows a critical error dialog if the file is empty or malformed.
            - Shows an informational dialog upon successful load.
        Returns:
            None
        """

        with open(file, "r") as f:
            data = yaml.safe_load(f)
        print(f"Loaded autosave data from {file}: {data}")
        if (
            not data
            or "test_scenario" not in data
            or not isinstance(data["test_scenario"], dict)
            or data.get("test_scenario", {}).get("test_id") is None
        ):
            QMessageBox.critical(self, "Load AutoSave", f"Empty autosave file: {file}")
            return
        self.schema_selected.emit(data)
        QMessageBox.information(self, "Load AutoSave", f"Loaded: {file}\n\n")

    def load_scenario(self, scenario_data: dict, fmt: str = "yaml") -> None:
        """
        Loads a test scenario from a selected YAML or JSON file.
        Description:
            - Opens a file dialog for the user to select a scenario file.
            - Supports YAML (.yaml, .yml) and JSON (.json) formats.
            - Parses the selected file and emits the scenario data via `schema_selected`.
            - Displays success or error messages based on the outcome.
        Arguments:
            scenario_data (dict): Placeholder for the scenario data to be loaded.
            fmt (str): Expected format of the file (e.g., 'yaml' or 'json').
        Body:
            - Uses `QFileDialog.getOpenFileName` to prompt file selection.
            - Validates file extension and loads content accordingly.
            - Emits the parsed data using `self.schema_selected.emit`.
            - Handles unsupported formats and file loading errors with message dialogs.
        Returns:
            None
        """

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select YAML or JSON file",
            "",
            "YAML Files (*.yaml *.yml);;JSON Files (*.json);;All Files (*)",
        )

        if not file_path:
            return  # Cancelled

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                if file_path.endswith((".yaml", ".yml")):
                    scenario_data = yaml.safe_load(f)
                elif file_path.endswith(".json"):
                    scenario_data = json.load(f)
                else:
                    QMessageBox.critical(
                        self, "Invalid File", "Please select a YAML or JSON file."
                    )
                    return
                self.schema_selected.emit(scenario_data)

            QMessageBox.information(self, "Success", f"Loaded {file_path}")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load file:\n{str(e)}")
