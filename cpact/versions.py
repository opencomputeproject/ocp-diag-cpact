"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

================================================================================
Version module for the YAML-based Test Execution Framework.
Stores and exposes framework version details.
================================================================================
"""

__version__ = "0.7"
__build__ = "2025.10.15"
__author__ = "Open Compute Project"
__tool_name__ = "Cloud Processor Accessibility Compliance Tool"


def get_version_info() -> str:
    """Return formatted version information."""
    return f"{__tool_name__} v{__version__} (Build: {__build__})"
