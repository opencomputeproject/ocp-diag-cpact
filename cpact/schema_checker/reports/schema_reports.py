"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.
===================================================================

schema_reports.py

Provides reporting and presentation utilities for schema validation results
within the CPACT Schema Validation Framework.

This module is responsible for transforming schema validation outcomes into
structured, human-readable formats suitable for console output, logs,
reports, and automated processing pipelines. It centralizes validation
reporting functionality to ensure consistent presentation of validation
results, diagnostics, warnings, and errors across all supported schema types.

The reporting layer consumes validation result models and generates
formatted summaries, detailed findings, tabular reports, and serialized
representations for CI/CD integration, troubleshooting, and auditing.

Key Features:
    - Display schema validation summaries.
    - Generate detailed validation reports.
    - Present validation findings in tabular format.
    - Export validation results as structured dictionaries or JSON.
    - Integrate with logging and automation workflows.

Classes:
    SchemaReporter:
        Provides utilities for formatting, displaying, and exporting
        schema validation results.

This implementation follows PEP 257 documentation standards and aligns
with CPACT framework coding and reporting conventions.
"""

import json
import os
import re
import textwrap
from dataclasses import asdict

from tabulate import tabulate

from cpact.schema_checker import ValidationResult
from cpact.utils.logger_utils import TestLogger


class SchemaReporter:
    """
    Responsible for presenting schema validation results in a structured
    and user-friendly format.

    This class provides methods for formatting, displaying, and exporting
    validation results generated during schema validation operations.
    It supports summary reporting, detailed diagnostics, tabular
    visualization, and machine-readable output formats.

    The reporter acts as the presentation layer between validation
    execution components and end users, ensuring validation findings
    are reported consistently across all schema types.

    Responsibilities:
        - Generate validation summary reports.
        - Display validation findings and diagnostics.
        - Format results into tables for readability.
        - Export validation results to JSON-compatible structures.
        - Integrate validation reporting with logging frameworks.
    """

    ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

    def __init__(self, logger=None):
        self.logger = logger or TestLogger().get_logger()

    def publish(self, result: ValidationResult):

        self.print(result)

        self.save(result)

        self.save_json(result)

    # ---------------------------------------------------------
    # Console
    # ---------------------------------------------------------

    def print(self, result: ValidationResult):

        if not result.results:
            self.logger.info("No validation results.")
            return

        self.logger.info(
            "\n"
            + "=" * 80
            + "\n"
            + "SCHEMA VALIDATION REPORT".center(80)
            + "\n"
            + "=" * 80
        )

        for validation in result.results:

            self.logger.info(f"\nRecipe         : {validation.recipe_name}")
            self.logger.info(f"Config         : {validation.config_name}")
            self.logger.info(f"Map File       : {validation.map_file}")
            self.logger.info(f"Schema Version : {validation.schema_version}")
            self.logger.info(f"Passed         : {validation.passed}")

            table = self._build_table(validation.entries)

            self.logger.info(table)

        self.logger.info("=" * 80)

    # ---------------------------------------------------------
    # TXT
    # ---------------------------------------------------------

    def save(
        self,
        result: ValidationResult,
        filename="schema_validation_report.txt",
    ):

        if not result.results:
            return

        path = os.path.join(
            TestLogger().get_log_dir(),
            filename,
        )

        with open(path, "w", encoding="utf-8") as fp:

            fp.write("=" * 80 + "\n")
            fp.write("SCHEMA VALIDATION REPORT\n")
            fp.write("=" * 80 + "\n\n")

            for validation in result.results:

                fp.write(f"Recipe         : {validation.recipe_name}\n")
                fp.write(f"Config         : {validation.config_name}\n")
                fp.write(f"Map File       : {validation.map_file}\n")
                fp.write(f"Schema Version : {validation.schema_version}\n")
                fp.write(f"Passed         : {validation.passed}\n\n")

                table = self._build_table(validation.entries)

                fp.write(self._strip_ansi(table))

                fp.write("\n")
                fp.write("-" * 80)
                fp.write("\n\n")

    # ---------------------------------------------------------
    # JSON
    # ---------------------------------------------------------

    def save_json(
        self,
        result: ValidationResult,
        filename="schema_validation_report.json",
    ):

        path = os.path.join(
            TestLogger().get_log_dir(),
            filename,
        )

        with open(path, "w", encoding="utf-8") as fp:

            json.dump(
                asdict(result),
                fp,
                indent=4,
            )

    # ---------------------------------------------------------
    # Table Builder
    # ---------------------------------------------------------

    def _build_table(self, entries):

        if not entries:
            return "No validation messages."

        rows = []

        for entry in entries:

            rows.append(
                {
                    "Category": entry.category,
                    "Collateral": entry.collateral,
                    "Status": self._color_status(entry.status),
                    "Message": self._wrap_text(entry.message),
                    "Path": self._wrap_text(entry.path),
                    "Line": entry.line,
                }
            )

        return tabulate(
            rows,
            headers="keys",
            tablefmt="grid",
        )

    # ---------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------

    @staticmethod
    def _wrap_text(text, width=40):

        if text is None:
            return ""

        return "\n".join(
            textwrap.wrap(
                str(text),
                width,
            )
        )

    @classmethod
    def _strip_ansi(cls, text):

        return cls.ANSI_ESCAPE.sub("", text)

    @staticmethod
    def _color_status(status):

        colors = {
            "SUCCESS": "\033[92m",
            "WARNING": "\033[93m",
            "ERROR": "\033[91m",
            "FAIL": "\033[91m",
        }

        reset = "\033[0m"

        return f"{colors.get(status, '')}{status}{reset}"
