"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

===========================================================================
DiagnosticAnalysisDialog is a PyQt5-based dialog for creating and editing diagnostic analysis entries
based on a dynamic JSON schema. It supports multiple schema variants using `oneOf`, and builds a
form interface with appropriate widgets for string, boolean, and enumerated types.

Features:
- Dynamically generates input fields based on schema definitions.
- Supports multiple diagnostic variants via `oneOf`.
- Highlights required fields with styled labels.
- Allows loading existing diagnostic data into the form.
- Returns structured user input as a list of dictionaries.

Attributes:
    data (dict): Preloaded diagnostic data to populate the form.
    diagnostic_schema (dict): JSON schema defining the structure of diagnostic entries.
    diagnostic_list (list): List of schema variants from `oneOf`.
    diagnostic_data (dict): Stores widget references for each schema variant.
    required (list): List of required fields for the current schema variant.

Usage:
    Instantiate DiagnosticAnalysisDialog with a schema and optional data.
    Use the dialog to input or edit diagnostic entries.
    Call `result()` to retrieve the structured output.
===========================================================================
"""
from PyQt5.QtWidgets import (
    QVBoxLayout,
    QWidget,
    QLineEdit,
    QComboBox,
    QDialogButtonBox,
    QDialog,
    QFormLayout,
    QCheckBox,
    QGroupBox,
)


class DiagnosticAnalysisDialog(QDialog):
    def __init__(
        self, parent: QWidget = None, data: dict = None, diagnostic_schema: dict = None
    ) -> None:
        """
        Initialize the DiagnosticAnalysisDialog.

        Args:
            parent (QWidget, optional): Parent widget. Defaults to None.

            data (dict, optional): Preloaded diagnostic data. Defaults to None.
            diagnostic_schema (dict, optional): JSON schema for diagnostics. Defaults to None.
        Returns:
            None
        """
        super().__init__(parent)
        self.setWindowTitle("Add / Edit Diagnostic Analysis")
        self.data = data or {}
        self.diagnostic_schema = diagnostic_schema or {}
        self.diagnostic_list = diagnostic_schema.get("oneOf", [])
        self.diagnostic_data = {}
        self.required = diagnostic_schema.get("required", [])
        self.build_ui()
        if data:
            self.load(data)

    def build_ui(self) -> None:
        """
        Builds the diagnostic analysis form layout dynamically based on the schema variants.

        Args:
            self (DiagnosticAnalysisDialog): The instance of the dialog class.

        Returns:
            None
        """
        layout = QVBoxLayout()
        form = QFormLayout()
        idx = 0
        for item in self.diagnostic_list:
            d_group = QGroupBox()
            d_group.setObjectName(
                "steps_card"
            )  # have 'card' in the objectName so the shadow helper picks it up
            d_group.setProperty("card", True)
            d_form = QFormLayout()
            self.diagnostic_data[idx] = {}
            for key, prop in item.get("properties", {}).items():
                self.required = item.get("required", [])
                label = f"{key} *" if key in self.required else key
                if key in self.required:
                    label = f"<b>{key}</b> <span style='color:red'>*</span>"
                if prop.get("type") == "string" and "enum" in prop:
                    combo = QComboBox()
                    combo.addItems(prop["enum"])
                    setattr(self, key, combo)
                    self.diagnostic_data[idx][key] = combo
                    d_form.addRow(label, combo)
                elif prop.get("type") == "boolean":
                    checkbox = QCheckBox()

                    self.diagnostic_data[idx][key] = checkbox
                    setattr(self, key, checkbox)
                    d_form.addRow(label, checkbox)
                else:
                    line_edit = QLineEdit()
                    setattr(self, key, line_edit)
                    self.diagnostic_data[idx][key] = line_edit
                    d_form.addRow(label, line_edit)
            idx += 1
            d_group.setLayout(d_form)
            layout.addWidget(d_group)

        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        ok_btn = buttons.button(QDialogButtonBox.Ok)
        if ok_btn:
            ok_btn.setProperty("role", "primary")

        cancel_btn = buttons.button(QDialogButtonBox.Cancel)
        if cancel_btn:
            cancel_btn.setProperty("role", "cancel")

        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.setLayout(layout)

    def load(self, d: dict) -> None:
        """
        Loads diagnostic analysis data into the form widgets.

        Args:
        d (dict): A dictionary containing diagnostic data mapped by index and field name.

        Returns:
        None
        """
         # Normalize the input into a dict with keys 0 and 1
        normalized_data = {}

        # --- Case 1: List of dicts ---
        if isinstance(d, list):
            for i, item in enumerate(d):
                if i in self.diagnostic_data and isinstance(item, dict):
                    matched_fields = {}
                    for key, widget in self.diagnostic_data[i].items():
                        for k, v in item.items():
                            if k == key or k.endswith(key) or key.endswith(k):
                                matched_fields[key] = v
                                break
                    normalized_data[i] = matched_fields

        # --- Case 2: Single dict ---
        elif isinstance(d, dict):
            # Find which diagnostic_data index has the most matching keys
            best_idx = None
            max_matches = 0

            for idx, field_map in self.diagnostic_data.items():
                match_count = sum(1 for k in d if k in field_map)
                if match_count > max_matches:
                    max_matches = match_count
                    best_idx = idx

            # Assign all matching fields to that best index
            if best_idx is not None:
                matched_fields = {}
                for key in self.diagnostic_data[best_idx]:
                    if key in d:
                        matched_fields[key] = d[key]
                normalized_data[best_idx] = matched_fields

        else:
            raise ValueError("Invalid input: expected dict or list of dicts")

        # --- Apply to widgets ---
        for idx, fields in self.diagnostic_data.items():
            row_data = normalized_data.get(idx, {})
            for key, widget in fields.items():
                value = row_data.get(key, "")
                if isinstance(widget, QLineEdit):
                    widget.setText(value)
                elif isinstance(widget, QComboBox):
                    widget.setCurrentText(value)
                elif isinstance(widget, QCheckBox):
                    widget.setChecked(bool(value))

    def result(self) -> list:
        """
        Collects and returns diagnostic analysis data entered in the form.

        Args:
            self (DiagnosticAnalysisDialog): The instance of the dialog class.

        Returns:
            list: A list of dictionaries containing field values for each diagnostic variant.
        """

        results = []
        for idx, fields in self.diagnostic_data.items():
            row_data = {}
            for key, widget in fields.items():
                if isinstance(widget, QLineEdit):
                    row_data[key] = widget.text()
                elif isinstance(widget, QComboBox):
                    row_data[key] = widget.currentText()
                elif isinstance(widget, QCheckBox):
                    row_data[key] = widget.isChecked()
            results.append(row_data)
        return results
