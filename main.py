"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cpact.main import main
from cpact.utils.custom_exception_handler import CustomExceptionHandler

if __name__ == "__main__":
    try:
        main()
        sys.exit(0)
    except Exception as e:
        CustomExceptionHandler.print_exception(e)
        sys.exit(1)
