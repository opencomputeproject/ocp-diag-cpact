"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

===============================================================================
OutputAnalysisDialog is a PyQt5-based dialog for creating and editing output analysis entries
based on a dynamic JSON schema. It builds a form interface with appropriate widgets for
string, boolean, and enumerated types, and supports loading and validating existing data.

Features:
- Dynamically generates input fields based on schema definitions.
- Highlights required fields with styled labels.
- Integrates with ExpandingTextEdit for adaptive multiline text input.
- Supports loading existing output analysis data into the form.
- Returns structured user input as a dictionary.

Attributes:
    data (dict): Preloaded output analysis data to populate the form.
    output_analysis_schema (dict): JSON schema defining the structure of output analysis entries.
    output_analysis_properties (dict): Extracted properties from the schema.
    output_analysis_data (dict): Stores widget references for each schema field.
    required (list): List of required fields for the output analysis entry.

Usage:
    Instantiate OutputAnalysisDialog with a schema and optional data.
    Use the dialog to input or edit output analysis entries.
    Call `result()` to retrieve the structured output.
===============================================================================
"""

from PyQt5.QtWidgets import (
    QVBoxLayout,
    QLineEdit,
    QComboBox,
    QDialogButtonBox,
    QDialog,
    QWidget,
    QFormLayout,
    QCheckBox,
)
from constants import ExpandingTextEdit


class OutputAnalysisDialog(QDialog):
    def __init__(
        self,
        parent: QWidget = None,
        data: dict = None,
        output_analysis_schema: dict = None,
    ) -> None:
        """
        Initializes the output analysis dialog with schema-driven form layout.

        Args:
            parent (QWidget): The parent widget for the dialog.
            data (dict): Preloaded output analysis data to populate the form.
            output_analysis_schema (dict): JSON schema defining the structure of output analysis entries.

        Returns:
            None
        """
        super().__init__(parent)
        self.setWindowTitle("Add / Edit Output Analysis")
        self.setFixedSize(400, 300)
        self.data = data or {}
        self.output_analysis_schema = output_analysis_schema or {}
        self.output_analysis_properties = self.output_analysis_schema.get(
            "properties", {}
        )
        self.output_analysis_data = {}
        self.required = self.output_analysis_schema.get("required", [])
        self.build_ui()
        if data:
            self.load(data)

    def build_ui(self) -> None:
        """
        Builds the output analysis form layout dynamically based on the provided schema.

        Args:
            self (OutputAnalysisDialog): The instance of the output analysis dialog class.

        Returns:
            None
        """
        layout = QVBoxLayout()
        form = QFormLayout()
        for key, prop in self.output_analysis_properties.items():
            label = key
            if key in self.required:
                label = f"<b>{key}</b> <span style='color:red'>*</span>"
            if prop.get("type") == "string" and "enum" in prop:
                combo = QComboBox()
                combo.addItems(prop["enum"])
                setattr(self, key, combo)
                self.output_analysis_data[key] = combo
                form.addRow(label, combo)
            elif prop.get("type") == "boolean":
                checkbox = QCheckBox()
                self.output_analysis_data[key] = checkbox
                setattr(self, key, checkbox)
                form.addRow(label, checkbox)
            else:
                line_edit = ExpandingTextEdit()
                setattr(self, key, line_edit)
                self.output_analysis_data[key] = line_edit
                form.addRow(label, line_edit)

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
        Loads output analysis data into the corresponding form widgets.

        Args:
            d (dict): A dictionary containing output analysis field values keyed by property name.

        Returns:
            None
        """
        for key, widget in self.output_analysis_data.items():
            if key in d:
                if isinstance(widget, ExpandingTextEdit):
                    widget.setPlainText(d[key])
                elif isinstance(widget, QComboBox):
                    widget.setCurrentText(d[key])
                elif isinstance(widget, QCheckBox):
                    widget.setChecked(bool(d[key]))

    def result(self) -> dict:
        """
        Collects and returns user input from the form as a dictionary.

        Args:
            self (OutputAnalysisDialog): The instance of the output analysis dialog class.

        Returns:
            dict: A dictionary containing output analysis field values keyed by property name.
        """
        data = {}
        for key, widget in self.output_analysis_data.items():
            if isinstance(widget, ExpandingTextEdit):
                data[key] = widget.toPlainText()
            elif isinstance(widget, QComboBox):
                data[key] = widget.currentText()
            elif isinstance(widget, QCheckBox):
                data[key] = widget.isChecked()
        return data
