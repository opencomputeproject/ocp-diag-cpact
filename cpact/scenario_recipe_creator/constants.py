"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

===========================================================================
This module provides reusable UI components, stylesheets, and utility functions for building
modern PyQt5-based desktop applications. It includes custom widgets such as a numbered list,
auto-expanding text editor, and animated buttons, along with styling constants for consistent
visual design across the application.

Features:
- `NumberedListWidget`: QListWidget with automatic numbering and drag-and-drop support.
- `ExpandingTextEdit`: QTextEdit that adjusts its height based on content.
- `HoverPushButton`: QPushButton with hover animation for enhanced UX.
- `MODERN_UI_QSS` and `TOOLBAR_QSS`: Qt stylesheet strings for modern UI theming.
- Utility functions:
    - `enable_hidpi_and_fonts`: Enables high-DPI scaling and font rendering.
    - `add_card_shadows`: Applies drop shadows to widgets marked as 'card'.
    - `make_button`: Creates a styled button with role-based appearance.
    - `show_error`: Displays a styled error message box.

Intended Use:
This module is designed to be imported into PyQt5 applications that require consistent styling,
interactive widgets, and enhanced user experience features.

Dependencies:
- PyQt5.QtWidgets
- PyQt5.QtCore
- PyQt5.QtGui
===========================================================================
"""

import os
import glob
import json
import yaml
from typing import Any
from PyQt5.QtCore import (
    Qt,
    QTimer,
    QRect,
    QPropertyAnimation,
    QEasingCurve,
    QCoreApplication,
)
from PyQt5.QtWidgets import (
    QWidget,
    QListWidget,
    QListWidgetItem,
    QTextEdit,
    QPushButton,
    QGraphicsDropShadowEffect,
    QFrame,
    QMessageBox,
)

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")
APP_ICON = os.path.join(ICON_DIR, "scenario_designer.ico")

MODERN_UI_QSS = r"""
/* ===== Global ===== */
* { outline: none; }
QWidget {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #f2f6fb, stop:1 #e9eef6);
    color: #0e2430;
    font-family: "Segoe UI", "Segoe UI Semilight", "Arial", sans-serif;
    font-size: 12px;
}

/* App header */
QWidget#app_header {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #ffffff, stop:1 #e6f0fb);
    border-bottom: 1px solid rgba(20,35,50,0.06);
    padding: 10px 12px;
}

/* Card / Group */
QFrame.card, QGroupBox.card {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #ffffff, stop:1 #f6f9fc);
    border: 1px solid rgba(16,40,60,0.06);
    border-radius: 10px;
    padding: 10px;
    margin: 6px;
}

/* GroupBox title */
QGroupBox.card::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 6px 10px;
    color: #153047;
    font-weight: 700;
    margin-top: -6px;
}

/* Labels */
QLabel.title { font-size: 12px; font-weight: 700; color: #123241; }
QLabel.subtitle { font-size: 12px; color: #4a6b7b; }

/* Inputs */
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #ffffff, stop:1 #f7fbff);
    border: 1px solid #cbd8e6;
    border-radius: 6px;
    padding: 6px 8px;
}
QLineEdit:focus, QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #69a7ff;
}

/* Buttons */
QPushButton {
    border-radius: 5px;
    padding: 4px 8px;   /* smaller padding */
    min-height: 20px;   /* was 25px */
    font-size: 11px;    /* slightly smaller font */
    font-weight: 600;
    border: 1px solid rgba(0,0,0,0.08);
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                                 stop:0 #fbfdff, stop:1 #eef6ff);
    color: #0f2433;
}
QPushButton:hover { /* instead of transform, use subtle border/background change */
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #eef6ff, stop:1 #e3f0ff);
    border: 1px solid rgba(30,120,230,0.12);
}
QPushButton:pressed {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #e6f0ff, stop:1 #d0e4ff);
}

/* Primary */
QPushButton[role="primary"] {
    color: white;
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #6fb0ff, stop:1 #2f7fed);
    border: 1px solid rgba(0,0,0,0.08);
}
QPushButton[role="primary"]:hover {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #86c3ff, stop:1 #3d86ff);
}

/* Icon-only toolbutton */
QToolButton.icon {
    border-radius: 6px;
    background: transparent;
    padding: 6px;
}
QToolButton.icon:hover {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #eef6ff, stop:1 #e3f0ff);
}

/* Lists/Tables */
QListWidget, QTreeView, QTableView {
    background: transparent;
    border: 1px solid #e1ecf6;
    border-radius: 6px;
    padding: 4px;
}
QListWidget::item {
    padding: 8px;
    border-radius: 6px;
    margin: 2px 0;
}
QListWidget::item:hover { background: #e8f4ff; }
QListWidget::item:selected { background: #2f7fed; color: white; }

/* Tabs */
QTabBar::tab {
    background: transparent;
    padding: 8px 12px;
    border-radius: 6px;
}
QTabBar::tab:selected {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #e9f3ff, stop:1 #d7ebff);
    font-weight: 700;
}

/* ProgressBar */
QProgressBar {
    border-radius: 6px;
    height: 12px;
    background: #ecf4fb;
    border: 1px solid #d7eaf8;
    text-align: center;
}
QProgressBar::chunk {
    border-radius: 6px;
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #7fb8ff, stop:1 #2f7fed);
}

/* Tooltip */
QToolTip {
    background-color: #f6fbff;
    color: #07202b;
    border: 1px solid #bcd7f3;
    padding: 6px;
    border-radius: 6px;
}

QWidget:disabled { color: #9aaeb8; background: #f6f8fb; }

/* ===== Role-based buttons ===== */

/* Base button look (keeps things consistent) */
QPushButton {
    border-radius: 5px;
    padding: 4px 8px;   /* smaller padding */
    min-height: 20px;   /* was 25px */
    font-size: 11px;    /* slightly smaller font */
    font-weight: 600;
    border: 1px solid rgba(0,0,0,0.08);
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                                 stop:0 #fbfdff, stop:1 #eef6ff);
    color: #0f2433;
}

/* Primary — blue */
QPushButton[role="primary"] {
    color: white;
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #6fb0ff, stop:1 #2f7fed);
    border: 1px solid rgba(30,90,200,0.18);
}
QPushButton[role="primary"]:hover {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #86c3ff, stop:1 #3d86ff);
}
QPushButton[role="primary"]:pressed {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #5f9de6, stop:1 #2568c4);
}

/* Edit — amber / warm accent */
QPushButton[role="edit"] {
    color: #16222a;
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #fff6e6, stop:1 #ffd76a);
    border: 1px solid rgba(160,120,40,0.12);
}
QPushButton[role="edit"]:hover {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #fff8e9, stop:1 #ffd990);
}
QPushButton[role="edit"]:pressed {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #ffe7b0, stop:1 #ffca3a);
}

/* Cancel — neutral / subtle */
QPushButton[role="cancel"] {
    color: #0f2433;
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #ffffff, stop:1 #f2f6fa);
    border: 1px solid rgba(30,40,60,0.06);
}
QPushButton[role="cancel"]:hover {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #f6f9fc, stop:1 #eaf4ff);
}
QPushButton[role="cancel"]:pressed {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #eef3fb, stop:1 #dfeafc);
}

/* Remove (danger) — red */
QPushButton[role="remove"] {
    color: white;
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #ff8b8b, stop:1 #e04a4a);
    border: 1px solid rgba(160,20,20,0.14);
}
QPushButton[role="remove"]:hover {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #ff9e9e, stop:1 #f15b5b);
}
QPushButton[role="remove"]:pressed {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #e37070, stop:1 #b83a3a);
}

"""

TOOLBAR_QSS = r"""
            QToolBar {
                background: #2c3e50;
                spacing: 6px;
                padding: 5px;
                border-bottom: 2px solid #1abc9c;
            }

            QToolButton {
                background: transparent;
                color: white;
                border: none;
                padding: 6px 10px;
                margin: 2px;
                border-radius: 6px;
            }
            QToolButton:hover {
                background: #34495e;
            }
            QToolButton:pressed {
                background: #1abc9c;
                color: black;
            }
            QToolButton:checked {
                background: #16a085;
                color: white;
            }
            QToolButton:disabled {
                background: transparent;
                color: #7f8c8d;
            }
        """

# Constants
ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")
APP_ICON = os.path.join(ICON_DIR, "scenario_designer.ico")

# -------------------------------
# Custom Widgets
# -------------------------------


class NumberedListWidget(QListWidget):
    """
    QListWidget that automatically numbers its items and supports drag-and-drop reordering.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setDragDropMode(QListWidget.InternalMove)
        self.model().rowsMoved.connect(self.renumber_items)

    def add_item_with_number(self, text: str) -> None:
        """
        Adds a new item to the list and renumbers all items.

        Args:
            text (str): The text content of the new item.
        """
        item = QListWidgetItem()
        item.setText(text)
        self.addItem(item)
        self.renumber_items()

    def renumber_items(self, *args: Any) -> None:
        """
        Renumbers all items in the list to maintain sequential numbering.
        """
        for i in range(self.count()):
            item = self.item(i)
            item.setText(f"{i + 1}. {item.text().split('. ', 1)[-1]}")


class ExpandingTextEdit(QTextEdit):
    """
    QTextEdit that automatically expands its height based on content.
    """

    def __init__(
        self, min_height: int = 60, max_height: int = 120, *args: Any, **kwargs: Any
    ) -> None:
        """
        Initializes the custom QTextEdit widget with adjustable height constraints.
        This constructor sets up the minimum and maximum height for the text edit widget, configures
        line wrapping to fit the widget's width, disables the vertical scroll bar, 
        and connects the text change event to automatically adjust the widget's height. 
        It also schedules an initial height adjustment after the widget is created.
        Args:
            min_height (int, optional): The minimum height of the text edit widget. Defaults to 60.
            max_height (int, optional): The maximum height of the text edit widget. Defaults to 120.
            *args (Any): Additional positional arguments passed to the base class.
            **kwargs (Any): Additional keyword arguments passed to the base class.
        Body:
            - Calls the superclass constructor with any additional arguments.
            - Sets the minimum and maximum height attributes.
            - Configures line wrapping and disables the vertical scroll bar.
            - Connects the textChanged signal to the adjust_height method.
            - Schedules an initial call to adjust_height after widget creation.
        Returns:
            None
        """

        super().__init__(*args, **kwargs)
        self.min_height = min_height
        self.max_height = max_height

        self.setLineWrapMode(QTextEdit.WidgetWidth)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.textChanged.connect(self.adjust_height)
        QTimer.singleShot(0, self.adjust_height)

    def adjust_height(self) -> None:
        """
        Adjusts the height of the text edit widget dynamically based on its content.
        Description:
            This method recalculates the height of the text edit widget according to the current
            content's document height. It ensures that the widget's height stays within the
            specified minimum and maximum bounds. If the content height is less than or equal to
            the minimum height, the widget is set to the minimum height and the vertical scroll bar
            is hidden. If the content height is between the minimum and maximum heights, the widget
            height is set to fit the content and the scroll bar is hidden. If the content height
            exceeds the maximum height, the widget is set to the maximum height and the scroll bar
            is enabled as needed.
        Arguments:
            None
        Body:
            - Calculates the document's height and adds a small padding.
            - Compares the calculated height with the widget's minimum and maximum height limits.
            - Sets the widget's height and vertical scroll bar policy accordingly.
        Returns:
            None

        """
        doc_height = int(self.document().size().height()) + 10

        if doc_height <= self.min_height:
            self.setFixedHeight(self.min_height)
            self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        elif doc_height < self.max_height:
            self.setFixedHeight(doc_height)
            self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        else:
            self.setFixedHeight(self.max_height)
            self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)


class HoverPushButton(QPushButton):
    """
    A QPushButton subclass that animates a "lift" effect when hovered.
    This button smoothly moves upward by a specified number of pixels when the mouse hovers over it,
    and returns to its original position when the mouse leaves. The animation duration and lift height
    can be customized.
    Arguments:
        *args: Positional arguments passed to the QPushButton constructor.
        lift_px (int, optional): Number of pixels to lift the button on hover. Default is 4.
        anim_ms (int, optional): Duration of the lift animation in milliseconds. Default is 120.
        **kwargs: Keyword arguments passed to the QPushButton constructor.
    Methods:
        enterEvent(event):
            Handles the mouse enter event. Animates the button upward by `lift_px` pixels.
            Args:
                event (object): The event object.
            Returns:
                None
        leaveEvent(event):
            Handles the mouse leave event. Animates the button back to its original position.
            Args:
                event (object): The event object.
            Returns:
                None
    """


    def __init__(self, *args: Any, lift_px: int = 4, anim_ms: int = 120, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._lift_px = lift_px
        self._anim_ms = anim_ms
        self._anim = QPropertyAnimation(self, b"geometry")
        self._anim.setEasingCurve(QEasingCurve.OutQuad)
        self._orig_geom = None

    def enterEvent(self, event: object) -> None:
        if self._orig_geom is None:
            self._orig_geom = self.geometry()
        g = self.geometry()
        target = QRect(g.x(), g.y() - self._lift_px, g.width(), g.height())
        self._anim.stop()
        self._anim.setDuration(self._anim_ms)
        self._anim.setStartValue(g)
        self._anim.setEndValue(target)
        self._anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event: object) -> None:
        if self._orig_geom is None:
            return super().leaveEvent(event)
        g = self.geometry()
        target = self._orig_geom
        self._anim.stop()
        self._anim.setDuration(self._anim_ms)
        self._anim.setStartValue(g)
        self._anim.setEndValue(target)
        self._anim.start()
        super().leaveEvent(event)


# -------------------------------
# Utility Functions
# -------------------------------


def enable_hidpi_and_fonts() -> None:
    """
    Enables high-DPI scaling and font rendering for better UI appearance.
    """
    try:
        QCoreApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QCoreApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    except Exception:
        pass


def add_card_shadows(root_widget: QWidget) -> None:
    """
    Applies drop shadows to QFrame widgets marked as 'card'.

    Args:
        root_widget (QWidget): The root widget to search for card frames.
    """

    def apply_shadow(widget: QFrame) -> None:
        effect = QGraphicsDropShadowEffect(widget)
        effect.setBlurRadius(18)
        effect.setColor(Qt.black)
        effect.setOffset(0, 6)
        widget.setGraphicsEffect(effect)

    for widget in root_widget.findChildren(QFrame):
        name = widget.objectName().lower()
        if "card" in name or widget.property("card") is True:
            apply_shadow(widget)


def make_button(text: str, role: str = "primary", group: QWidget = None) -> QPushButton:
    """
    Creates a styled QPushButton with hover animation.

    Args:
        text (str): Button label.
        role (str): Role for styling (e.g., 'primary', 'edit', 'cancel', 'remove').
        group (QWidget): Optional parent widget.

    Returns:
        QPushButton: The styled button.
    """
    button = HoverPushButton(text, parent=group)
    button.setProperty("role", role)
    return button


def show_error(parent: QWidget, text: str) -> int:
    """
    Displays a styled error message box with a red 'OK' button.

    Args:
        parent (QWidget): The parent widget.
        text (str): The error message to display.

    Returns:
        int: The result of the message box execution.
    """
    msg = QMessageBox(parent)
    msg.setIcon(QMessageBox.Critical)
    msg.setWindowTitle("Error")
    msg.setText(text)

    ok_btn = QPushButton("OK")
    ok_btn.setProperty("role", "remove")
    msg.addButton(ok_btn, QMessageBox.AcceptRole)

    return msg.exec_()
