"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

===============================================================================
EntryCriteriaDialog is a PyQt5-based dialog for creating and editing entry criteria records
based on a dynamic JSON schema. It builds a form interface with appropriate widgets for
string, boolean, and enumerated types, and supports loading and validating existing data.

Features:
- Dynamically generates input fields based on schema definitions.
- Highlights required fields with styled labels.
- Integrates with ExpandingTextEdit for adaptive multiline text input.
- Supports loading existing entry criteria data into the form.
- Automatically triggers form submission when preloaded data is present.
- Returns structured user input as a dictionary.

Attributes:
    data (dict): Preloaded entry criteria data to populate the form.
    entry_criteria_schema (dict): JSON schema defining the structure of entry criteria.
    entry_criteria_data (dict): Stores widget references for each schema field.
    required (list): List of required fields for the entry criteria.
    load_entry_criteria_data (dict): Optional data to preload and auto-submit.

Usage:
    Instantiate EntryCriteriaDialog with a schema and optional data.
    Use the dialog to input or edit entry criteria entries.
    Call `result()` to retrieve the structured output.
===============================================================================
"""
from PyQt5.QtWidgets import (
    QVBoxLayout,
    QLineEdit,
    QComboBox,
    QWidget,
    QDialogButtonBox,
    QDialog,
    QFormLayout,
    QCheckBox,
    QTextEdit,
)

from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QFontMetrics
from PyQt5.QtCore import Qt

from constants import ExpandingTextEdit


class EntryCriteriaDialog(QDialog):
    def __init__(
        self,
        parent: QWidget = None,
        data: dict = None,
        entry_criteria_schema: dict = None,
        load_entry_criteria_data: dict = None,
    ) -> None:
        """
        Initializes the entry criteria dialog with schema-driven form layout.

        Args:
            parent (QWidget): The parent widget for the dialog.
            data (dict): Preloaded entry criteria data to populate the form.
            entry_criteria_schema (dict): JSON schema defining the structure of entry criteria entries.
            load_entry_criteria_data (dict): Optional data to preload and auto-submit.

        Returns:
            None
        """
        super().__init__(parent)
        self.setWindowTitle("Add / Edit Entry Criteria")
        self.setFixedSize(500, 300)
        self.data = data or {}
        self.entry_criteria_schema = (
            entry_criteria_schema.get("items", {}).get("properties", {}) or {}
        )
        self.entry_criteria_data = {}
        self.load_entry_criteria_data = load_entry_criteria_data
        self.required = entry_criteria_schema.get("items", {}).get("required", [])
        self.build_ui()
        if data:
            self.load(data)

    def build_ui(self) -> None:
        """
        Builds the entry criteria form layout dynamically based on the provided schema.

        Args:
            self (EntryCriteriaDialog): The instance of the entry criteria dialog class.

        Returns:
            None
        """
        layout = QVBoxLayout()
        form = QFormLayout()
        for key, prop in self.entry_criteria_schema.items():
            label = f"{key} *" if key in self.required else key
            if key in self.required:
                label = f"<b>{key}</b> <span style='color:red'>*</span>"
            if prop.get("type") == "string" and "enum" in prop:
                combo = QComboBox()
                combo.addItems(prop["enum"])
                setattr(self, key, combo)
                self.entry_criteria_data[key] = combo
                form.addRow(label, combo)
            elif prop.get("type") == "boolean":
                checkbox = QCheckBox()
                self.entry_criteria_data[key] = checkbox
                setattr(self, key, checkbox)
                form.addRow(label, checkbox)
            else:
                line_edit = ExpandingTextEdit()
                setattr(self, key, line_edit)
                self.entry_criteria_data[key] = line_edit
                form.addRow(label, line_edit)
                line_edit.adjust_height()

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
        if self.load_entry_criteria_data:
            self.load(self.load_entry_criteria_data)
            QTimer.singleShot(0, ok_btn.click)

    def load(self, d: dict) -> None:
        """
        Loads entry criteria data into the corresponding form widgets.

        Args:
            d (dict): A dictionary containing entry criteria field values keyed by property name.

        Returns:
            None
        """
        for key, widget in self.entry_criteria_data.items():
            if key in d:
                if isinstance(widget, ExpandingTextEdit):
                    widget.setPlainText(d[key])
                elif isinstance(widget, QComboBox):
                    widget.setCurrentText(d[key])
                elif isinstance(widget, QCheckBox):
                    widget.setChecked(bool(d[key]))

    def result(self) -> dict:
        """
        Collects and returns entry criteria data from the form widgets.

        Args:
            self (EntryCriteriaDialog): The instance of the entry criteria dialog class.

        Returns:
            dict: A dictionary containing field values keyed by property name.
        """
        data = {}
        for key, widget in self.entry_criteria_data.items():
            if isinstance(widget, ExpandingTextEdit):
                data[key] = widget.toPlainText()
            elif isinstance(widget, QComboBox):
                data[key] = widget.currentText()
            elif isinstance(widget, QCheckBox):
                data[key] = widget.isChecked()
        return data
