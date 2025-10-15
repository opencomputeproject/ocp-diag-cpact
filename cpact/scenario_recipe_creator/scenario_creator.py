"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

===============================================================================
scenario_creator.py
A PyQt5-based application for dynamically loading JSON schemas and generating forms for scenario design.
    - SchemaLoader: A QWidget dialog for selecting and loading a JSON schema file. Emits a signal with the loaded schema.
    - RecipeCreator: External widget (imported) for creating recipe forms based on the loaded schema.
Features:
    - Modern UI styling and accessibility enhancements.
    - High-DPI and font support for improved appearance.
    - Soft card shadows for visual polish.
    - Windows-specific application ID for proper taskbar grouping.
Classes:
    SchemaLoader(QWidget):
        A widget for selecting and loading a JSON schema file.
            schema (dict or None): The currently loaded schema.
            label (QLabel): UI label prompting schema selection.
            load_schema(): Opens a file dialog, loads the selected JSON schema, emits schema_selected signal.
Usage:
    Run the script to launch the Scenario Designer. Select a JSON schema file to build a form. Upon successful loading, the RecipeCreator widget is launched for further scenario creation.
Note:
    Requires PyQt5 and supporting modules (constants.py, recipe_create_widget.py).
A PyQt5-based application to load JSON schemas and create forms dynamically.

Modules:
- SchemaLoader: Widget to select and load a JSON schema.
- RecipeCreator: External widget to create recipe forms based on schema.
===============================================================================
"""

import os
import sys
import json
import ctypes
import platform
from PyQt5.QtWidgets import QApplication, QStyleFactory
from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QLabel,
    QFileDialog,
    QMessageBox,
)
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QStyleFactory

# imports (add these if not already present)
from PyQt5.QtGui import QFontDatabase, QIcon
from PyQt5.QtGui import QIcon
from constants import (
    make_button,
    MODERN_UI_QSS,
    enable_hidpi_and_fonts,
    add_card_shadows,
    APP_ICON,
)
from recipe_create_widget import RecipeCreator

if platform.system() == "Windows":
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
        "ScenarioDesigner.App.1.0"
    )


class SchemaLoader(QWidget):
    """A QWidget-based dialog for loading a JSON schema file.
    This class provides a simple UI for selecting a JSON schema file from disk.
    Upon successful loading, it emits the `schema_selected` signal with the loaded schema as a dictionary.
    Signals:
        schema_selected (dict): Emitted when a schema is successfully loaded.
    Attributes:
        schema (dict or None): The currently loaded schema, or None if not loaded.
        label (QLabel): Label prompting the user to select a schema.
        load_btn (QPushButton): Button to trigger schema selection.
    Methods:
        load_schema(): Opens a file dialog to select a JSON schema file, loads it, and emits the schema_selected signal.
    """

    schema_selected = pyqtSignal(dict)  # signal to emit selected schema

    def __init__(self) -> None:
        """
        Initializes the SchemaLoader widget and sets up the UI components and layout.

        Args:
            self (SchemaLoader): The instance of the SchemaLoader class.

        Returns:
            None
        """
        super().__init__()
        # self.setWindowTitle("Schema Loader")
        self.setWindowTitle("Scenario Designer")  # App title
        self.setWindowIcon(QIcon(APP_ICON))  # App icon
        self.schema = None
        layout = QVBoxLayout()

        self.label = QLabel("Select a JSON Schema to build the form.")
        layout.addWidget(self.label)

        self.load_btn = make_button("Select Schema", "primary")
        self.load_btn.clicked.connect(self.load_schema)
        layout.addWidget(self.load_btn)

        self.setLayout(layout)

    def load_schema(self) -> None:
        """
        Opens a file dialog to load a JSON schema and emits it via the `schema_selected` signal.

        Args:
            self (QDialog): The instance of the dialog class.

        Returns:
            None
        """
        default_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "spec",
            "schema"
        )
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Schema", default_path, "JSON Files (*.json)"
        )
        if not path:
            return
        try:
            with open(path, "r") as f:
                self.schema = json.load(f)
            self.schema_selected.emit(self.schema)  # emit signal
            self.close()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load schema:\n{e}")


def main() -> None:
    """
    Main entry point for the application.
    """
    enable_hidpi_and_fonts()
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(APP_ICON))

    # set preferred style
    for s in ("WindowsVista", "Windows", "Fusion"):
        if s in QStyleFactory.keys():
            app.setStyle(QStyleFactory.create(s))
            break

    app.setStyleSheet(MODERN_UI_QSS)

    schema_loader = SchemaLoader()
    add_card_shadows(schema_loader)  # add soft shadows to marked cards

    def handle_schema(schema: dict) -> None:
        """
        Initializes and displays the RecipeCreator window with the provided schema.
        Args:
            schema (dict): The schema data to be used for creating the recipe.
        Returns:
            None
        """

        recipe_window = RecipeCreator(schema)
        recipe_window.resize(800, 800)
        recipe_window.show()

    schema_loader.schema_selected.connect(handle_schema)
    schema_loader.resize(400, 200)
    schema_loader.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
