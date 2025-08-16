"""
Copyright (c) Microsoft Corporation.
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.
"""

import logging
import os
import json
from pathlib import Path
from datetime import datetime
from colorlog import ColoredFormatter

class TestLogger:
    """
    A singleton-based logger utility class for managing logging in a test environment.
    This class provides a centralized logging mechanism with both console and file handlers.
    It ensures that only one instance of the logger exists throughout the application.
    Attributes:
        _instance (TestLogger): The singleton instance of the logger.
        log_dir (str): The directory where log files are stored.
        log_file (str): The path to the log file.
        logger (logging.Logger): The logger instance used for logging messages.
    Methods:
        __new__(cls, log_dir=None):
            Ensures that only one instance of the class is created (singleton pattern).
        __init__(self, log_dir=None):
            Initializes the logger instance, setting up console and file handlers.
            Creates a log directory and log file if not provided.
        get_logger(self):
            Returns the logger instance.
        get_log_dir(self):
            Returns the directory where log files are stored.
        get_log_file(self):
            Returns the path to the log file.
        cleanup(self):
            Cleans up the logger by flushing and closing all handlers and shutting down logging.
    
    """
    
    _instance = None

    def __new__(cls, log_dir=None):
        if cls._instance is None:
            cls._instance = super(TestLogger, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, log_dir=None):
        if self._initialized:
            return  # Already initialized
        self.log_dir = log_dir
        print("log_dir", log_dir)
        self.logger = logging.getLogger("test_logger")
        self.logger.setLevel(logging.DEBUG)
        self.logger.propagate = False  # Prevent duplicate output via root logger

        # Determine log directory
        if not log_dir:
            print("No log directory provided. Using default.")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_dir = os.path.join("logs", f"test_run_{timestamp}")
        else:
            print(f"Using provided log directory: {log_dir}")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_dir = os.path.join(log_dir, f"test_run_{timestamp}")
        os.makedirs(log_dir, exist_ok=True)

        log_file = os.path.join(log_dir, "test_run.log")
        self.log_dir = log_dir
        self.log_file = log_file

        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_formatter = ColoredFormatter(
        "[%(log_color)s%(levelname)s%(reset)s] %(message)s",
            log_colors={
                "DEBUG": "cyan",
                "INFO": "green",
                "WARNING": "yellow",
                "ERROR": "red",
                "CRITICAL": "bold_red",
            },
        )
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)

        # File handler
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        file_handler.setFormatter(file_formatter)
        self.logger.addHandler(file_handler)

        self.logger.info(f"📁 Log directory created: {log_dir}")
        self.logger.info(f"📝 Logging to file: {log_file}")

        self._initialized = True

    def get_logger(self):
        return self.logger

    def get_log_dir(self):
        return self.log_dir

    def get_log_file(self):
        return self.log_file

    def cleanup(self):
        for handler in self.logger.handlers[:]:
            handler.flush()
            handler.close()
            self.logger.removeHandler(handler)
        logging.shutdown()


class JsonWriter:
    """
    A class to handle writing Python objects to a JSON file in a
    structured and human-readable format.

    This class is designed to be used as a context manager (with the 'with'
    statement) to ensure that the file is always closed properly.
    """

    def __init__(self, file_path: Path | str):
        """
        Initializes the JsonWriter.

        Args:
            file_path (Path | str): The full path to the output JSON file.
        """
        self.file_path = Path(file_path)
        self._file_handle = None

    def __enter__(self):
        """
        Opens the file for writing when entering the 'with' block.
        This allows the object to be used as a context manager.
        """
        # Ensure the parent directory exists
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        # Open the file and store the handle
        self._file_handle = open(self.file_path, "w", encoding="utf-8")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Closes the file when exiting the 'with' block.
        This is called automatically, even if errors occur inside the block.
        """
        if self._file_handle:
            self._file_handle.close()

    def write(self, data: dict | list):
        """
        Serializes the given Python object to JSON and writes it to the file.

        Args:
            data (dict | list): The Python dictionary or list to write.

        Raises:
            IOError: If the writer is used outside of a 'with' block.
            TypeError: If the data cannot be serialized to JSON.
        """
        if not self._file_handle or self._file_handle.closed:
            raise IOError("JsonWriter must be used within a 'with' statement.")

        # Use json.dump() to write the data to the file handle.
        # `indent=4` makes the JSON output human-readable.
        json.dump(data, self._file_handle, indent=4)
        # Add a newline for clean separation if writing multiple objects (optional)
        self._file_handle.write('\n')