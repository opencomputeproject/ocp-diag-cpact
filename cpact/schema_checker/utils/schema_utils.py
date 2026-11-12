"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

============================================================================================

Provides utility functions for locating and retrieving schema-related
resources within the CPACT Schema Validation Framework.

This module centralizes schema discovery logic and abstracts file-system
operations required to access schema versions and schema definition files.
It ensures that validators and orchestration components can consistently
resolve schema locations without duplicating path-management logic.

The utility methods support:

- Resolving the active schema directory.
- Selecting a specific schema version when requested (unknown versions are
  rejected rather than silently replaced).
- Defaulting to the latest available schema version when none is given.
- Constructing schema definition file paths for supported schema types.

Classes
--------
SchemaUtils
    Collection of helper methods for schema directory and schema file
    resolution.

Design Goals
------------
- Centralize schema path resolution logic.
- Eliminate hardcoded schema directory references.
- Support version-based schema validation workflows.
- Simplify validator implementation by abstracting file-system operations.
- Improve maintainability and extensibility of schema management.

This implementation follows PEP 257 documentation conventions and aligns
with CPACT framework coding standards.
"""

import os


class SchemaUtils:
    """
    Utility class providing helper methods for schema discovery and
    path resolution.

    The class is responsible for locating schema directories and
    generating schema file paths used during validation operations.
    It supports both explicit schema version selection and automatic
    resolution of the latest available schema version.

    Responsibilities
    ----------------
    - Resolve schema root directories.
    - Retrieve version-specific schema locations.
    - Generate schema definition file paths.
    - Provide a centralized location for schema-related utilities.
    """

    @staticmethod
    def get_schema_dir(
        schema_version: str | None = None,
    ) -> str:
        """
        Retrieve the schema directory for a specified schema version.

        If ``schema_version`` is given it must match an available version
        directory; otherwise the most recent version (compared numerically,
        so ``0.10`` is newer than ``0.9``) is returned.

        Args:
            schema_version (str | None, optional):
                Target schema version to retrieve. If not provided, the latest
                schema version is used.

        Returns:
            str:
                Absolute path to the resolved schema directory.

        Raises:
            FileNotFoundError:
                If the schema root directory does not exist.
            ValueError:
                If ``schema_version`` is given but no such version exists.

        Notes:
            Available schema versions are determined by enumerating
            version directories under the framework schema root.
        """

        root = os.path.join(
            os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            ),
            "spec",
            "schema",
        )

        versions = SchemaUtils.available_versions(root)
        if not versions:
            raise FileNotFoundError(f"No schema versions found under {root}")

        if schema_version not in (None, ""):
            version = str(schema_version).strip()
            if version not in versions:
                raise ValueError(
                    f"Unsupported schema_version '{version}'. "
                    f"Available versions: {', '.join(versions)}"
                )
        else:
            version = versions[-1]

        return os.path.join(root, version)

    @staticmethod
    def available_versions(root: str) -> list[str]:
        """Return the version directories under ``root``, oldest first."""

        def version_key(name: str) -> tuple:
            parts = []
            for part in name.split("."):
                parts.append((0, int(part), "") if part.isdigit() else (1, 0, part))
            return tuple(parts)

        return sorted(
            (
                name
                for name in os.listdir(root)
                if os.path.isdir(os.path.join(root, name))
            ),
            key=version_key,
        )

    @staticmethod
    def get_schema_file(
        schema_dir: str,
        schema_type: str,
    ) -> str:
        """
        Construct the schema definition file path for a given schema type.

        Args:
            schema_dir (str):
                Path to the schema version directory.

            schema_type (str):
                Schema category identifier, such as ``config`` or
                ``scenario``.

        Returns:
            str:
                Fully qualified path to the schema definition file.

        Example:
            >>> SchemaUtils.get_schema_file(
            ...     "/spec/schema/v1.0",
            ...     "config"
            ... )
            '/spec/schema/v1.0/config_recipe_schema.json'
        """

        recipe_schema = os.path.join(
            schema_dir,
            f"{schema_type}_recipe_schema.json",
        )
        if os.path.exists(recipe_schema):
            return recipe_schema

        # Some schema types (e.g. config) are published as <type>_schema.json
        plain_schema = os.path.join(schema_dir, f"{schema_type}_schema.json")
        return plain_schema if os.path.exists(plain_schema) else recipe_schema
