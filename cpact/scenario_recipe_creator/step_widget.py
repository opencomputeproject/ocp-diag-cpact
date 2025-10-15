"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

===============================================================================
StepDialog is a PyQt5-based dialog for creating and editing test step entries within a scenario designer
application. It dynamically builds form fields based on a JSON schema and supports nested components such as
entry criteria, output analysis, and diagnostic analysis. The dialog adapts its layout based on the selected
step type and validates required fields before submission.

Features:
- Dynamically generates UI fields based on schema definitions and selected step type.
- Supports conditional rendering of step-type-specific fields.
- Integrates with custom widgets for entry criteria, output analysis, and diagnostics.
- Provides file browsing for path-based inputs.
- Validates required fields and displays styled error messages.
- Collects and returns structured user input as a dictionary.

Attributes:
    data (dict): Preloaded step data to populate the form.
    step_schema (dict): JSON schema defining the structure of the step.
    docker_list (list): List of available Docker containers for selection.
    step_data (dict): Stores widget references for base step fields.
    step_type_data (dict): Stores widget references for step-type-specific fields.
    diagnostic_widgets (list): List of diagnostic analysis widgets.
    output_analysis_widgets (list): List of output analysis widgets.
    entry_criteria_widgets (list): List of entry criteria widgets.
    connection_dependant (list): List of fields dependent on the connection type.
    connection_dependent_widgets (dict): Mapping of connection-dependent fields to widgets.
    required (list): List of required fields for the step.

Usage:
    Instantiate StepDialog with a schema and optional data.
    Use the dialog to input or edit test step entries.
    Call `result()` to retrieve the structured output.
===============================================================================
"""

from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTextEdit,
    QComboBox,
    QGroupBox,
    QFileDialog,
    QListWidget,
    QListWidgetItem,
    QDialogButtonBox,
    QDialog,
    QFormLayout,
    QCheckBox,
    QScrollArea,
    QSizePolicy,
)
from PyQt5.QtCore import Qt

from constants import make_button, show_error
from diagnostic_analysis_widget import DiagnosticAnalysisDialog
from output_analysis_widget import OutputAnalysisDialog
from entry_criteria_widget import EntryCriteriaDialog
from PyQt5.QtCore import QTimer
from constants import NumberedListWidget


class StepDialog(QDialog):
    def __init__(
        self,
        parent: QWidget = None,
        data: dict = None,
        step_schema: dict = None,
        docker_list: list = None,
        load_step_data: dict = None,
    ) -> None:
        """
        Initializes the step dialog with schema-driven form layout.

        Args:
            parent (QWidget): The parent widget for the dialog.
            data (dict): Preloaded step data to populate the form.
            step_schema (dict): JSON schema defining the structure of step entries.
            docker_list (list): List of available Docker containers for selection.
            load_step_data (dict): Optional data to preload and auto-submit.
        Returns:
            None
        """
        super().__init__(parent)
        self.setWindowTitle("Add / Edit Step")
        self.resize(750, 970)
        self.data = data or {}
        self.docker_list = docker_list or []
        self.step_schema = step_schema or {}
        self.load_step_data = load_step_data
        self.step_data = {}
        self.step_type_data = {}
        self.diagnostic_widgets = []
        self.output_analysis_widgets = []
        self.entry_criteria_widgets = []
        self.step_type = None
        self.connection_dependant = ["method", "body", "headers"]
        self.connection_dependent_widgets = {}
        self.required = self.step_schema.get("required", []) if self.step_schema else []
        self.build_ui()
        if data:
            self.load(data)

    def build_ui(self) -> None:
        """
        Builds the step form layout dynamically based on the provided schema.
        Adds input widgets for each property and configures role-based buttons.
        Args:
            self (StepDialog): The instance of the step dialog class.
        Returns:
            None
        """
        self.layout = QVBoxLayout()
        form = QFormLayout()
        command_type_schema = self.step_schema.get("allOf", [])
        step_properties = self.step_schema.get("properties", {})
        for key, prop in step_properties.items():
            label = key
            if key in self.required:
                label = f"<b>{key}</b> <span style='color:red'>*</span>"
            if key in ["entry_criteria", "output_analysis", "diagnostics_analysis"]:
                continue
            if key == "container_name":
                combo = QComboBox()
                container_names = [d.get("container_name") for d in self.docker_list]
                container_names = ["None"] + container_names
                combo.addItems(container_names)
                setattr(self, key, combo)
                self.step_data[key] = combo
                form.addRow(label, combo)
                continue
            if prop.get("type") == "string" and "enum" in prop:

                combo = QComboBox()
                combo.addItems(prop["enum"])
                setattr(self, key, combo)
                self.step_data[key] = combo
                form.addRow(label, combo)
                if key == "step_type":
                    self.step_type = combo
                    combo.currentTextChanged.connect(
                        lambda val, s=command_type_schema: self.on_step_type_change(
                            val, s
                        )
                    )
                if key == "connection":
                    combo.currentTextChanged.connect(self.change_connection_state)
            elif prop.get("type") == "boolean":
                checkbox = QCheckBox()
                self.step_data[key] = checkbox
                setattr(self, key, checkbox)
                form.addRow(label, checkbox)
            else:
                line_edit = QLineEdit()
                setattr(self, key, line_edit)
                self.step_data[key] = line_edit
                form.addRow(label, line_edit)

        self.layout.addLayout(form)
        load_entry_criteria_data = (
            self.load_step_data.get("entry_criteria") if self.load_step_data else None
        )
        entry_criteria_scheme = step_properties.get("entry_criteria", {})
        # Entry Criteria Section
        if entry_criteria_scheme:
            ec_group = QGroupBox("Entry Criteria")
            ec_group.setObjectName(
                "steps_card"
            )  # have 'card' in the objectName so the shadow helper picks it up
            ec_group.setProperty("card", True)
            ec_group.setFixedHeight(150)
            ec_layout = QVBoxLayout()
            self.ec_list = NumberedListWidget()
            ec_buttons = QHBoxLayout()
            add_ec = make_button("Add Entry Criteria", "primary", group=ec_group)
            add_ec.clicked.connect(
                lambda: self.add_entry_criteria(entry_criteria_scheme)
            )
            edit_ec = make_button("Edit Entry Criteria", "edit", group=ec_group)
            edit_ec.clicked.connect(
                lambda: self.edit_entry_criteria(entry_criteria_scheme)
            )
            remove_ec = make_button("Remove Entry Criteria", "remove", group=ec_group)
            remove_ec.clicked.connect(self.remove_entry_criteria)
            ec_buttons.addWidget(add_ec)
            ec_buttons.addWidget(edit_ec)
            ec_buttons.addWidget(remove_ec)
            ec_layout.addWidget(self.ec_list)
            ec_layout.addLayout(ec_buttons)

            ec_group.setLayout(ec_layout)
            self.layout.addWidget(ec_group)
        if load_entry_criteria_data:
            for item in load_entry_criteria_data:
                self.add_entry_criteria(entry_criteria_scheme, item)
        self.dynamic_area = QVBoxLayout()
        self.dynamic_container = QWidget()
        self.dynamic_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self.dynamic_container.setLayout(self.dynamic_area)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.dynamic_container)
        self.layout.addWidget(scroll)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        ok_btn = buttons.button(QDialogButtonBox.Ok)
        if ok_btn:
            ok_btn.setProperty("role", "primary")

        cancel_btn = buttons.button(QDialogButtonBox.Cancel)
        if cancel_btn:
            cancel_btn.setProperty("role", "cancel")

        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.layout.addWidget(buttons)
        self.setLayout(self.layout)

        self.on_step_type_change(
            self.step_type.currentText(), command_schema=command_type_schema
        )
        if self.load_step_data:
            self.load(self.load_step_data)
            QTimer.singleShot(0, ok_btn.click)

    def add_entry_criteria(
        self, entry_criteria_schema: dict = None, item_data: dict = None
    ) -> None:
        """
        Opens a dialog to add an entry criteria item and validates required fields.
        Args:
            self (StepDialog): The instance of the step dialog class.
            entry_criteria_schema (dict): The schema defining the structure of entry criteria items.
            item_data (dict): Optional data to preload into the dialog for editing.
        Returns:
            None
        """
        dialog = EntryCriteriaDialog(
            self,
            entry_criteria_schema=entry_criteria_schema,
            load_entry_criteria_data=item_data,
        )
        if dialog.exec_() == QDialog.Accepted:
            d = dialog.result()
            keys = list(
                entry_criteria_schema.get("items", {}).get("required", {}) or []
            )
            if not all(k in d and d.get(k) for k in keys):
                show_error(self, f'All fields required: {", ".join(keys)}')
                return
            name = f"{d.get(keys[0], '')}" if keys else "Item-"
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, d)
            self.ec_list.addItem(item)

    def edit_entry_criteria(self, entry_criteria_schema: dict = None) -> None:
        item = self.ec_list.currentItem()
        keys = list(entry_criteria_schema.keys())
        if not item:
            show_error(self, "Select an entry criteria to edit")
            return
        d = item.data(Qt.UserRole)
        dlg = EntryCriteriaDialog(self, d, entry_criteria_schema=entry_criteria_schema)
        if dlg.exec_() == QDialog.Accepted:
            nd = dlg.result()
            keys = list(
                entry_criteria_schema.get("items", {}).get("required", {}) or []
            )
            if not all(k in nd and nd.get(k) for k in keys):
                show_error(self, f'All fields required: {", ".join(keys)}')
                return
            name = f"{nd.get(keys[0], '')}" if keys else "Item-"
            item.setText(name)
            item.setData(Qt.UserRole, nd)

    def remove_entry_criteria(self) -> None:
        """
        Removes the selected entry criteria item.
        Args:
            self (StepDialog): The instance of the step dialog class.
        Returns:
            None
        """
        item = self.ec_list.currentItem()
        if not item:
            show_error(self, "Select an entry criteria to remove")
            return
        self.ec_list.takeItem(self.ec_list.row(item))

    def get_properties_for_step(self, schema: list, step_type_value: str) -> tuple:
        """
        Retrieves the schema properties and required fields for a given step type.
        Args:
            self (StepDialog): The instance of the step dialog class.
            schema (list): The list of schema definitions for different step types.
            step_type_value (str): The selected step type value.
        Returns:
            tuple: A tuple containing the properties dictionary and required fields list.
        """
        for rule in schema:
            step_type = (
                rule.get("if", {})
                .get("properties", {})
                .get("step_type", {})
                .get("const")
            )
            if step_type == step_type_value:
                return rule.get("then", {}).get("properties", {}), rule.get(
                    "then", {}
                ).get("required", [])

        return {}, []

    def on_step_type_change(self, step_type: str, command_schema: list = None) -> None:
        """
        Rebuilds the dynamic UI section based on the selected step type.
        Args:
            self (StepDialog): The instance of the step dialog class.
            step_type (str): The selected step type value.
            command_schema (list): The list of schema definitions for different step types.
        Returns:
            None
        """
        for attr_name in ("diag_list", "out_list", "path_box"):
            old = getattr(self, attr_name, None)
            if old is not None:
                try:
                    if hasattr(old, "clear"):
                        old.clear()
                    old.deleteLater()
                except Exception:
                    pass
                try:
                    delattr(self, attr_name)
                except Exception:
                    setattr(self, attr_name, None)

        # remove widgets that are children of dynamic_area
        for i in reversed(range(self.dynamic_area.count())):
            widget = self.dynamic_area.itemAt(i).widget()
            if widget:
                widget.setParent(None)

        for d in list(self.step_type_data.keys()):
            if d in self.step_data:
                del self.step_data[d]
        self.step_type_data.clear()
        self.diagnostic_widgets.clear()
        self.output_analysis_widgets.clear()

        # --- continue with original logic to get properties and build UI ---
        step_properties, required_properties = self.get_properties_for_step(
            command_schema, step_type
        )

        g = QGroupBox(f"{step_type} Fields")
        g.setObjectName(
            "steps_card"
        )  # have 'card' in the objectName so the shadow helper picks it up
        g.setProperty("card", True)
        f = QFormLayout()
        g.setLayout(f)
        connection = self.step_data.get("connection", None)
        for key, value in step_properties.items():
            label = key
            if key in required_properties:
                label = f"<b>{key}</b> <span style='color:red'>*</span>"
            if key in ["output_analysis", "diagnostic_analysis"]:
                continue
            if key == "expected_output":
                text_edit = QTextEdit()
                text_edit.setFixedHeight(80)
                setattr(self, key, text_edit)
                self.step_type_data[key] = text_edit
                f.addRow(QLabel(label), text_edit)
                continue
            if (
                key == "expected_output_path"
                or key == "log_analysis_path"
                or key == "scenario_path"
            ):
                path_layout = QHBoxLayout()
                path_box = QLineEdit()
                path_box.setPlaceholderText(f"Select {key.replace('_', ' ')} file...")

                browse_btn = make_button("Browse", "primary", group=g)
                # make sure browse_file updates this particular path box
                browse_btn.clicked.connect(
                    lambda _, pb=path_box: self.browse_file_for(pb)
                )

                path_layout.addWidget(path_box)
                path_layout.addWidget(browse_btn)
                setattr(self, key, path_box)
                # keep a stable attribute for the browse callback too
                self.path_box = path_box
                self.step_type_data[key] = path_box
                f.addRow(QLabel(label), path_layout)
                continue
            if value.get("type") == "string" and "enum" in value:
                combo = QComboBox()
                combo.addItems(value["enum"])
                setattr(self, key, combo)
                self.step_type_data[key] = combo
                f.addRow(QLabel(label), combo)
            elif value.get("type") == "boolean":
                checkbox = QCheckBox()
                self.step_type_data[key] = checkbox
                setattr(self, key, checkbox)
                f.addRow(QLabel(label), checkbox)
            else:

                line_edit = QLineEdit()
                setattr(self, key, line_edit)
                self.step_type_data[key] = line_edit
                f.addRow(QLabel(label), line_edit)
                connection_value = None
                if key == "duration":
                    line_edit.setText("30")  # default duration 30 seconds
                if key == "loop":
                    line_edit.setText("1")  # default loop 1 time
                if key in self.connection_dependant:
                    self.connection_dependent_widgets[key] = line_edit
                if connection:
                    connection_value = (
                        connection.currentText()
                        if isinstance(connection, QLineEdit)
                        else str(connection)
                    )
                if connection_value != "redfish" and key in self.connection_dependant:
                    line_edit.setEnabled(False)
                    line_edit.setStyleSheet(
                        "QLineEdit { background-color: lightgray; color: gray; }"
                    )

        self.step_data.update(self.step_type_data)
        self.dynamic_area.addWidget(g)
        g.adjustSize()
        self.dynamic_area.parentWidget().adjustSize()

        output_analysis = step_properties.get("output_analysis", {})
        if output_analysis:
            output_analysis_schema = output_analysis.get("items", {})
            if output_analysis_schema:
                self.handle_output_analysis(output_analysis_schema)

        diagnostic_analysis = step_properties.get("diagnostic_analysis", {})
        if diagnostic_analysis:
            diagnostic_schema = diagnostic_analysis.get("items", {})
            self.handle_diagnostic_analysis(diagnostic_schema)

    def change_connection_state(self, connection_value: str) -> None:
        """
        Enables or disables connection-dependent fields based on the selected connection.
        Args:
            self (StepDialog): The instance of the step dialog class.
            connection_value (str): The selected connection type value.
        Returns:
            None
        """
        for key, widget in self.connection_dependent_widgets.items():
            if connection_value == "redfish":
                widget.setEnabled(True)
                widget.setStyleSheet("")
            else:
                widget.setEnabled(False)
                widget.setStyleSheet(
                    "QLineEdit { background-color: lightgray; color: gray; }"
                )
                widget.clear()

    def browse_file_for(self, path_box: QLineEdit) -> None:
        """
        Opens a file dialog and sets the selected path in the given QLineEdit.
        Args:
            self (StepDialog): The instance of the step dialog class.
            path_box (QLineEdit): The QLineEdit widget to set the selected file path.
        Returns:
            None
        """
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Log File",
            "",
            "Log Files (*.log);;Text Files (*.txt);;All Files (*)",
        )
        if file_path:
            path_box.setText(file_path)

    # keep backward-compatible browse_file for any callers expecting it
    def browse_file(self) -> None:
        """
        Fallback method to browse files using the default path box.
        Args:
            self (StepDialog): The instance of the step dialog class.
        Returns:
            None
        """
        # fallback: set the main self.path_box if available
        if hasattr(self, "path_box"):
            self.browse_file_for(self.path_box)

    def handle_diagnostic_analysis(self, diagnostic_schema: dict) -> None:
        """
        Initializes the diagnostic analysis section and its controls.
        Args:
            self (StepDialog): The instance of the step dialog class.
            diagnostic_schema (dict): The schema defining the structure of diagnostic analysis items.
        Returns:
            None
        """
        diag_box = QGroupBox("Diagnostic Analysis")
        diag_box.setObjectName(
            "steps_card"
        )  # have 'card' in the objectName so the shadow helper picks it up
        diag_box.setProperty("card", True)
        diag_box.setFixedHeight(150)
        diag_layout = QVBoxLayout()
        self.diag_list = NumberedListWidget()
        diag_buttons = QHBoxLayout()
        add_diag = make_button("Add Diagnostic Analysis", "primary", group=diag_box)
        add_diag.clicked.connect(
            lambda: self.add_diagnostic_analysis(diagnostic_schema)
        )
        edit_diag = make_button("Edit Diagnostic Analysis", "edit", group=diag_box)
        edit_diag.clicked.connect(
            lambda: self.edit_diagnostic_analysis(diagnostic_schema)
        )
        remove_diag = make_button(
            "Remove Diagnostic Analysis", "remove", group=diag_box
        )
        remove_diag.clicked.connect(self.remove_diagnostic_analysis)
        diag_buttons.addWidget(add_diag)
        diag_buttons.addWidget(edit_diag)
        diag_buttons.addWidget(remove_diag)
        diag_layout.addWidget(self.diag_list)
        diag_layout.addLayout(diag_buttons)
        diag_box.setLayout(diag_layout)
        self.dynamic_area.addWidget(diag_box)

    def add_diagnostic_analysis(self, diagnostic_schema: dict) -> None:
        """
        Opens a dialog to add a diagnostic analysis entry and validates required fields.

        Args:
            self (StepDialog): The instance of the step dialog class.
            diagnostic_schema (dict): The schema defining the structure of diagnostic analysis items.
        Returns:
            None
        """
        dialog = DiagnosticAnalysisDialog(self, diagnostic_schema=diagnostic_schema)
        diag_items = diagnostic_schema.get("oneOf", [])
        required_fields = []
        for i in diag_items:
            required_fields.append(i.get("required") or [None])
        if dialog.exec_() == QDialog.Accepted:
            d = dialog.result()
            res = self.validate_required_fields(d, required_fields)
            if not res[0]:
                show_error(self, res[1])
                return
            name = self.build_display_name(d, required_fields)
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, d)
            self.diag_list.addItem(item)

    def edit_diagnostic_analysis(self, diagnostic_schema: dict = None) -> None:
        """
        Opens a dialog to edit the selected diagnostic analysis entry.
        Args:
            self (StepDialog): The instance of the step dialog class.
            diagnostic_schema (dict): The schema defining the structure of diagnostic analysis items.
        Returns:
            None
        """
        item = self.diag_list.currentItem()
        diag_items = diagnostic_schema.get("oneOf", [])
        required_fields = []
        for i in diag_items:
            required_fields.append(i.get("required") or [None])
        if not item:
            show_error(self, "Select a diagnostic analysis to edit")
            return
        d = item.data(Qt.UserRole)
        dlg = DiagnosticAnalysisDialog(
            self, data=d, diagnostic_schema=diagnostic_schema
        )
        if dlg.exec_() == QDialog.Accepted:
            nd = dlg.result()
            res = self.validate_required_fields(nd, required_fields)
            if not res[0]:
                show_error(self, res[1])
                return
            name = self.build_display_name(nd, required_fields)
            item.setText(name)
            item.setData(Qt.UserRole, nd)

    def remove_diagnostic_analysis(self) -> None:
        """
        Removes the selected diagnostic analysis entry.
        Args:
            self (StepDialog): The instance of the step dialog class.
        Returns:
            None
        """
        item = self.diag_list.currentItem()
        if not item:
            show_error(self, "Select a diagnostic analysis to remove")
            return
        self.diag_list.takeItem(self.diag_list.row(item))

    def build_display_name(self, data: dict, required_fields: list[list[str]]) -> str:
        """
        Return a readable display name for a diagnostic entry based on satisfied required fields.
        Args:
            self (StepDialog): The instance of the step dialog class.
            data (dict): The diagnostic entry data.
            required_fields (list): List of required field groups.
        Returns:
            str: The constructed display name.
        """
        for row in data:
            for group in required_fields:
                if all(row.get(f) for f in group):  # group satisfied
                    # join non-empty fields with " - "
                    return " - ".join(row[f] for f in group if row.get(f))
            # fallback if nothing matched
        return "Unnamed"

    def validate_required_fields(
        self, data: dict, required_fields: list[list[str]]
    ) -> tuple[bool, str]:
        """
        Validate that at least one required field group is satisfied.
        Args:
            self (StepDialog): The instance of the step dialog class.
            data (dict): The diagnostic entry data.
            required_fields (list): List of required field groups.
        Returns:
            tuple: A tuple containing a boolean indicating validation success and a message.
        """
        satisfied_groups = []
        errors = []
        missings = []
        for row in data:
            for group in required_fields:
                missing = [f for f in group if not row.get(f)]
                if not missing:  # all fields present for this group
                    missings.append("True")
                    satisfied_groups.append(group)
                else:
                    missings.append("False")
                    errors.append(f"Group {group} missing: {missing}")

        if not satisfied_groups and all(m == "False" for m in missings):
            return (
                False,
                "❌ None of the required field groups are fully satisfied.\n"
                + "\n".join(errors),
            )

            # If one or more groups are satisfied, that's OK
        return True, "✅ Validation passed"

    def handle_output_analysis(self, output_analysis_schema: dict) -> None:
        """
        Initializes the output analysis section and its controls.
        Args:
            self (StepDialog): The instance of the step dialog class.
            output_analysis_schema (dict): The schema defining the structure of output analysis items.
        Returns:
            None
        """
        out_box = QGroupBox("Output Analysis")
        out_box.setObjectName(
            "steps_card"
        )  # have 'card' in the objectName so the shadow helper picks it up
        out_box.setProperty("card", True)
        out_box.setFixedHeight(150)
        out_layout = QVBoxLayout()
        self.out_list = NumberedListWidget()
        out_buttons = QHBoxLayout()
        add_out = make_button("Add Output Analysis", "primary", group=out_box)
        add_out.clicked.connect(
            lambda: self.add_output_analysis(output_analysis_schema)
        )
        edit_out = make_button("Edit Output Analysis", "edit", group=out_box)
        edit_out.clicked.connect(
            lambda: self.edit_output_analysis(output_analysis_schema)
        )
        remove_out = make_button("Remove Output Analysis", "remove", group=out_box)
        remove_out.clicked.connect(self.remove_output_analysis)
        out_buttons.addWidget(add_out)
        out_buttons.addWidget(edit_out)
        out_buttons.addWidget(remove_out)
        out_layout.addWidget(self.out_list)
        out_layout.addLayout(out_buttons)
        out_box.setLayout(out_layout)
        self.dynamic_area.addWidget(out_box)

    def add_output_analysis(self, output_analysis_schema: dict) -> None:
        """
        Opens a dialog to add an output analysis entry and validates required fields.
        Args:
            self (StepDialog): The instance of the step dialog class.
            output_analysis_schema (dict): The schema defining the structure of output analysis items.
        Returns:
            None
        """
        dialog = OutputAnalysisDialog(
            self, output_analysis_schema=output_analysis_schema
        )
        required_fields = output_analysis_schema.get("required", [])
        if dialog.exec_() == QDialog.Accepted:
            d = dialog.result()
            if not all(d.get(k) for k in required_fields):
                show_error(self, f'All fields required: {", ".join(required_fields)}')
                return
            name = f"{d.get(required_fields[0], '')} - {d.get(required_fields[1], '')}"
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, d)
            self.out_list.addItem(item)

    def edit_output_analysis(self, output_analysis_schema=None) -> None:
        """
        Opens a dialog to edit the selected output analysis entry.

        Args:
            self (StepDialog): The instance of the step dialog class.
            output_analysis_schema (dict): The schema defining the structure of output analysis items.
        Returns:
            None
        """
        item = self.out_list.currentItem()
        required_fields = output_analysis_schema.get("required", [])
        if not item:
            show_error(self, "Select an output analysis to edit")
            return
        d = item.data(Qt.UserRole)
        dlg = OutputAnalysisDialog(
            self, d, output_analysis_schema=output_analysis_schema
        )
        if dlg.exec_() == QDialog.Accepted:
            nd = dlg.result()
            name = (
                f"{nd.get(required_fields[0], '')} - {nd.get(required_fields[1], '')}"
            )
            item.setText(name)
            item.setData(Qt.UserRole, nd)

    def remove_output_analysis(self) -> None:
        """
        Removes the selected output analysis entry.
        Args:
            self (StepDialog): The instance of the step dialog class.
        Returns:
            None
        """
        item = self.out_list.currentItem()
        if not item:
            show_error(self, "Select an output analysis to remove")
            return
        self.out_list.takeItem(self.out_list.row(item))

    def load(self, d: dict) -> None:
        """
        Robustly populate the dialog from the saved dict `d`.
        Supports items that are dicts OR lists (e.g. diagnostic entries that are lists of dicts).
        """

        def format_item_name(item_data: object) -> str:
            """Return a readable display name for a saved item (dict, list, or scalar)."""
            parts = []
            if isinstance(item_data, dict):
                for v in item_data.values():
                    if v is not None and v != "":
                        parts.append(str(v))
            elif isinstance(item_data, list):
                # list may contain dicts or scalars
                for el in item_data:
                    if isinstance(el, dict):
                        for v in el.values():
                            if v is not None and v != "":
                                parts.append(str(v))
                    else:
                        if el is not None and el != "":
                            parts.append(str(el))
            else:
                # fallback for other types
                if item_data is not None and item_data != "":
                    parts.append(str(item_data))

            if not parts:
                return "Unnamed"
            # keep it reasonably short in the UI
            return " - ".join(parts[:6])

        # Set step_type first so on_step_type_change builds the dynamic widgets
        if "step_type" in d and isinstance(
            self.step_data.get("step_type", None), QComboBox
        ):
            try:
                self.step_data["step_type"].setCurrentText(d["step_type"])
            except Exception:
                # ignore invalid step_type values
                pass

        # Rebuild dynamic area based on the selected step_type
        if isinstance(self.step_data.get("step_type", None), QComboBox):
            self.on_step_type_change(
                self.step_data["step_type"].currentText(),
                self.step_schema.get("allOf", []),
            )

        # Populate basic fields (text, combos, checkboxes)
        for key, widget in self.step_data.items():
            if key not in d:
                continue
            try:
                if isinstance(widget, QTextEdit):
                    widget.setPlainText(str(d.get(key, "")))
                elif isinstance(widget, QLineEdit):
                    widget.setText(str(d.get(key, "")))
                elif isinstance(widget, QComboBox):
                    widget.setCurrentText(str(d.get(key, "")))
                elif isinstance(widget, QCheckBox):
                    widget.setChecked(bool(d.get(key, False)))
            except Exception:
                # be defensive: some widgets may have been recreated; ignore errors
                pass

        # Populate entry criteria list (if created in build_ui)
        if hasattr(self, "ec_list") and self.ec_list is not None:
            self.ec_list.clear()
            for item_data in d.get("entry_criteria", []) or []:
                name = format_item_name(item_data)
                item = QListWidgetItem(name)
                item.setData(Qt.UserRole, item_data)
                self.ec_list.addItem(item)

        # Populate diagnostic list (if created)
        if hasattr(self, "diag_list") and self.diag_list is not None:
            self.diag_list.clear()
            for item_data in d.get("diagnostic_analysis", []) or []:
                name = format_item_name(item_data)
                item = QListWidgetItem(name)
                item.setData(Qt.UserRole, item_data)
                self.diag_list.addItem(item)

        # Populate output analysis list (if created)
        if hasattr(self, "out_list") and self.out_list is not None:
            self.out_list.clear()
            for item_data in d.get("output_analysis", []) or []:
                name = format_item_name(item_data)
                item = QListWidgetItem(name)
                item.setData(Qt.UserRole, item_data)
                self.out_list.addItem(item)

    def result(self) -> dict:
        data = {}
        for key, widget in self.step_data.items():
            if isinstance(widget, QTextEdit):
                data[key] = widget.toPlainText()
            elif isinstance(widget, QLineEdit):
                data[key] = widget.text()
            elif isinstance(widget, QComboBox):
                data[key] = widget.currentText()
            elif isinstance(widget, QCheckBox):
                data[key] = widget.isChecked()

        # collect entry criteria items (if present)
        if hasattr(self, "ec_list"):
            ec_items = []
            for i in range(self.ec_list.count()):
                it = self.ec_list.item(i)
                ec_items.append(it.data(Qt.UserRole))
            data["entry_criteria"] = ec_items

        # collect diagnostic analysis items (if present)
        if hasattr(self, "diag_list"):
            diag_items = []
            for i in range(self.diag_list.count()):
                it = self.diag_list.item(i)
                diag_items.append(it.data(Qt.UserRole))
            data["diagnostic_analysis"] = diag_items

        # collect output analysis items (if present)
        if hasattr(self, "out_list"):
            out_items = []
            for i in range(self.out_list.count()):
                it = self.out_list.item(i)
                out_items.append(it.data(Qt.UserRole))
            data["output_analysis"] = out_items

        return data
