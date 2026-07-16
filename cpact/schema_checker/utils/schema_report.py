"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.
===================================================================

schema_report.py

Provides formatting and reporting utilities for schema validation results
within the CPACT Schema Validation Framework.

This module is responsible for transforming validation findings into
well-structured, human-readable reports suitable for console output,
log files, and automated validation workflows. It consolidates validation
results from multiple schema categories and presents them in a tabular
format with consistent styling and severity highlighting.

The reporting functionality includes text wrapping, severity formatting,
report generation, and persistence of validation summaries to log files,
enabling improved troubleshooting, auditing, and CI/CD integration.

Classes:
    ValidationReportFormatter:
        Utility class for formatting and presenting schema validation
        reports in console and file outputs.

Key Features:
    - Generate structured validation reports.
    - Format validation findings into readable tables.
    - Apply severity-based status highlighting.
    - Wrap long messages for improved report readability.
    - Export validation reports to persistent log files.

This implementation follows PEP 257 documentation conventions and aligns
with CPACT framework coding and reporting standards.

"""

import os
import textwrap
from typing import List, Dict

from tabulate import tabulate

from cpact.result_builder.result_builder import ResultCollector
from cpact.utils.logger_utils import TestLogger


class ValidationReportFormatter:
    """
    Formats and presents schema validation results.

    This utility class provides methods for converting validation findings
    into structured, readable reports for console and file-based output.
    It supports text formatting, status highlighting, report aggregation,
    and persistence of validation reports for diagnostics and auditing.

    Responsibilities:
        - Format validation data into tabular reports.
        - Improve readability through text wrapping.
        - Apply severity highlighting to validation statuses.
        - Display validation reports through the logging framework.
        - Persist validation reports to log files.

    All methods are designed to support consistent reporting behavior
    across CPACT schema validation workflows.
    """

    @staticmethod
    def wrap_text(text, width=30):
        """
        Wrap long text values into multiple lines.

        This utility method formats lengthy strings by inserting line breaks
        at the specified width to improve readability when displayed in
        tabular reports.

        Args:
            text (Any):
                Text value to wrap.
            width (int, optional):
                Maximum number of characters per line.
                Defaults to 30.

        Returns:
            str:
                Wrapped text with newline separators. Returns an empty string
                if the input value is None.
        """
        if text is None:
            return ""

        return "\n".join(textwrap.wrap(str(text), width))

    @classmethod
    def print_validation_report(
        cls,
        report: List[List[Dict[str, str]]],
        logger,
    ) -> None:
        """
        Generate and display a formatted schema validation report.

        This method converts validation findings into a tabular format,
        applies severity highlighting, and outputs the report through
        the provided logger. A plain-text version of the report is also
        persisted to a log file for audit and troubleshooting purposes.

        Args:
            report (List[List[Dict[str, str]]]):
                Collection of validation sections containing validation
                entries grouped by category.
            logger:
                Logger instance used to display report output.

        Returns:
            None

        Notes:
            - Validation statuses are colorized using ResultCollector.
            - Long field values are automatically wrapped for readability.
            - Reports are written to
            'schema_validation_report.txt' in the configured log directory.
            - If no validation findings exist, a success message is logged.
        """

        if not report:
            logger.info("No issues found.")
            return

        all_rows = []

        for section in report:
            first = True

            for row in section:
                r = row.copy()

                for k in r:
                    r[k] = cls.wrap_text(r[k], 30)

                if "Status" in r:
                    r["Status"] = ResultCollector.get_instance().color_severity(
                        r["Status"]
                    )

                if not first:
                    r["Category"] = ""
                    r["Colateral"] = ""

                first = False
                all_rows.append(r)

        table_lines = tabulate(
            all_rows,
            headers="keys",
            tablefmt="grid",
        )

        logger.info(f"""
================================================================
                    VALIDATION REPORT
================================================================
{table_lines}
================================================================
""")

        log_path = os.path.join(
            TestLogger().get_log_dir(),
            "schema_validation_report.txt",
        )

        with open(log_path, "w", encoding="utf-8") as f:
            f.write("VALIDATION REPORT\n")
            f.write("=" * 80 + "\n")
            f.write(ResultCollector().clean_ansi(table_lines))
            f.write("\n" + "=" * 80)
