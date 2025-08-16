"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.
"""

import os
import json
import yaml

def load_yaml_file(file_path):
    """
    Load a YAML or JSON test scenario file and return the data as a Python dict/list.
    """
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    ext = os.path.splitext(file_path)[1].lower()

    with open(file_path, "r") as f:
        if ext in [".yaml", ".yml"]:
            try:
                return yaml.safe_load(f)
            except yaml.YAMLError as e:
                raise ValueError(f"Invalid YAML format in {file_path}: {e}")
        elif ext == ".json":
            try:
                return json.load(f)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON format in {file_path}: {e}")
        else:
            raise ValueError(f"Unsupported file type: {ext}")


def convert_yaml_to_json(yaml_path, output_dir=None):
    """
    Convert a YAML file to a JSON file in the same or specified directory.
    Returns the path to the created JSON file.
    """
    data = load_yaml_file(yaml_path)
    base_name = os.path.splitext(os.path.basename(yaml_path))[0]
    output_dir = output_dir or os.path.dirname(yaml_path)
    output_file = os.path.join(output_dir, f"{base_name}.json")

    with open(output_file, "w") as f:
        json.dump(data, f, indent=2)

    return output_file
