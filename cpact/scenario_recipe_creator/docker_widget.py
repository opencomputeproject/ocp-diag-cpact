"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

===============================================================================
DockerDialog is a PyQt5-based dialog for creating and editing Docker container entries
based on a dynamic JSON schema. It builds a form interface with appropriate widgets
for string, boolean, and enumerated types, and supports loading and validating existing data.

Features:
- Dynamically generates input fields based on schema definitions.
- Highlights required fields with styled labels.
- Supports loading existing Docker data into the form.
- Automatically triggers form submission when preloaded data is present.
- Returns structured user input as a dictionary.

Attributes:
    data (dict): Preloaded Docker data to populate the form.
    docker_schema (dict): JSON schema defining the structure of Docker entries.
    docker_properties (dict): Extracted properties from the schema.
    docker_data (dict): Stores widget references for each schema field.
    required (list): List of required fields for the Docker entry.
    load_docker_data (dict or list): Optional data to preload and auto-submit.

Usage:
    Instantiate DockerDialog with a schema and optional data.
    Use the dialog to input or edit Docker container entries.
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

from PyQt5.QtCore import QTimer


class DockerDialog(QDialog):
    def __init__(
        self,
        parent: QWidget = None,
        data: dict = None,
        docker_schema: dict = None,
        load_docker_data: dict = None,
    ) -> None:
        """
        Initializes the Docker dialog with schema-driven form layout.

        Args:
            parent (QWidget): The parent widget for the dialog.
            data (dict): Preloaded Docker data to populate the form.
            docker_schema (dict): JSON schema defining the structure of Docker entries.
            load_docker_data (dict): Optional data to preload and auto-submit.

        Returns:
            None
        """
        super().__init__(parent)
        self.setWindowTitle("Add / Edit Docker Entry")
        self.setFixedSize(400, 300)
        self.load_docker_data = load_docker_data or []
        self.data = data or {}
        self.docker_schema = docker_schema or {}
        self.docker_properties = self.docker_schema.get("properties", {})
        self.docker_data = {}
        self.required = self.docker_schema.get("required", [])
        self.build_ui()
        if data:
            self.load(data)

    def build_ui(self) -> None:
        """
        Builds the Docker entry form layout dynamically based on the provided schema.

        Args:
            self (DockerDialog): The instance of the DockerDialog class.

        Returns:
            None
        """
        layout = QVBoxLayout()
        form = QFormLayout()
        for key, prop in self.docker_properties.items():
            label = f"{key} *" if key in self.required else key
            if key in self.required:
                label = f"<b>{key}</b> <span style='color:red'>*</span>"
            if prop.get("type") == "string" and "enum" in prop:
                combo = QComboBox()
                combo.addItems(prop["enum"])
                setattr(self, key, combo)
                self.docker_data[key] = combo
                # if key in self.load_docker_data:
                #     combo.setCurrentText(self.load_docker_data[key])
                form.addRow(label, combo)

            elif prop.get("type") == "boolean":
                checkbox = QCheckBox()
                self.docker_data[key] = checkbox
                setattr(self, key, checkbox)
                # if key in self.load_docker_data:
                #     checkbox.setChecked(bool(self.load_docker_data[key]))
                form.addRow(label, checkbox)

            else:
                line_edit = QLineEdit()
                setattr(self, key, line_edit)
                self.docker_data[key] = line_edit
                # if key in self.load_docker_data:
                #     line_edit.setText(self.load_docker_data[key])
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
        if self.load_docker_data:
            self.load(self.load_docker_data)
            QTimer.singleShot(0, ok_btn.click)
        layout.addWidget(buttons)
        self.setLayout(layout)

    def load(self, d: dict) -> None:
        """
        Loads Docker entry data into the corresponding form widgets.

        Args:
            d (dict): A dictionary containing Docker field values keyed by property name.

        Returns:
            None
        """
        for key, widget in self.docker_data.items():
            if key in d:
                if isinstance(widget, QLineEdit):
                    widget.setText(d[key])
                elif isinstance(widget, QComboBox):
                    widget.setCurrentText(d[key])
                elif isinstance(widget, QCheckBox):
                    widget.setChecked(bool(d[key]))

    def result(self) -> dict:
        """
        Collects and returns Docker entry data from the form widgets.

        Args:
            self (DockerDialog): The instance of the DockerDialog class.

        Returns:
            dict: A dictionary containing field values keyed by property name.
        """
        data = {}
        for key, widget in self.docker_data.items():
            if isinstance(widget, QLineEdit):
                data[key] = widget.text()
            elif isinstance(widget, QComboBox):
                data[key] = widget.currentText()
            elif isinstance(widget, QCheckBox):
                data[key] = widget.isChecked()
        return data
