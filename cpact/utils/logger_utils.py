"""
Copyright (c) Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

===============================================================================
TestLogger is a singleton-based logging utility designed for structured logging in test environments.
It supports both console and file output with color-coded formatting and integrates with OCP TV output
for enhanced traceability of test runs and diagnostics.

Features:
- Singleton pattern ensures consistent logging across modules.
- Console and file handlers with colored output and timestamped logs.
- Automatic log directory creation with timestamped naming.
- Integration with OCP TV output via OCPTVFileWriter.
- Context-managed JSON writing via JsonWriter.

Classes:
    TestLogger:
        Manages logging setup and lifecycle.
        Provides access to logger, log directory, and log file.
        Supports cleanup of handlers and shutdown.

    JsonWriter:
        Context manager for writing structured JSON data to file.
        Ensures safe file handling and human-readable formatting.

    OCPTVFileWriter:
        Custom writer for OCP TV JSON messages.
        Logs key test events and diagnostics to both file and logger.

Attributes:
    _instance (TestLogger): Singleton instance of the logger.
    log_dir (str): Directory where logs are stored.
    log_file (str): Path to the main log file.
    timestamp (str): Timestamp used for naming log files.

Usage:
    Use `TestLogger()` to initialize logging.
    Use `JsonWriter` in a `with` block to safely write JSON.
    Use `OCPTVFileWriter` to log structured test events and diagnostics.
===============================================================================
"""

import logging
import os
import json
from pathlib import Path
from datetime import datetime
from colorlog import ColoredFormatter
import ocptv.output as tv
from typing import Dict, Any


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

    def __new__(cls, log_dir: str = None) -> "TestLogger":
        if cls._instance is None:
            cls._instance = super(TestLogger, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, log_dir: str = None) -> None:
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

        self.timestamp = timestamp
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

    def get_logger(self) -> logging.Logger:
        return self.logger

    def get_log_dir(self) -> str:
        return self.log_dir

    def get_log_file(self) -> str:
        return self.log_file

    def get_timestamp(self) -> str:
        return self.timestamp

    def cleanup(self) -> None:
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

    def __init__(self, file_path: Path | str) -> None:
        """
        Initializes the JsonWriter.

        Args:
            file_path (Path | str): The full path to the output JSON file.
        """
        self.file_path = Path(file_path)
        self._file_handle = None

    def __enter__(self) -> "JsonWriter":
        """
        Opens the file for writing when entering the 'with' block.
        This allows the object to be used as a context manager.
        """
        # Ensure the parent directory exists
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        # Open the file and store the handle
        self._file_handle = open(self.file_path, "w", encoding="utf-8")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """
        Closes the file when exiting the 'with' block.
        This is called automatically, even if errors occur inside the block.
        """
        if self._file_handle:
            self._file_handle.close()

    def write(self, data: dict | list) -> None:
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
        self._file_handle.write("\n")


class OCPTVFileWriter(tv.Writer):
    """
    Custom OCP TV Writer that integrates with TestLogger for structured logging.

    This writer outputs OCP TV JSON messages to separate files while maintaining
    integration with the existing TestLogger infrastructure.
    """

    def __init__(self, test_logger: TestLogger, test_name: str = "ocptv_test") -> None:
        """
        Initialize the OCP TV file writer.

        Args:
            test_logger (TestLogger): Instance of TestLogger for directory management
            test_name (str): Name of the test for file naming
        """
        self.test_logger = test_logger
        self.test_name = test_name

        # Create OCP TV specific log file path
        timestamp = test_logger.get_timestamp()
        ocptv_file = os.path.join(
            test_logger.get_log_dir(), f"ocptv_{test_name}_{timestamp}.json"
        )

        self.ocptv_file = ocptv_file
        self.logger = test_logger.get_logger()

        # Ensure the file exists and is ready for writing
        Path(self.ocptv_file).touch()

        self.logger.info(f"🔧 OCP TV output file: {self.ocptv_file}")

    def write(self, buffer: str) -> None:
        """
        Write OCP TV JSON message to the log file.

        Args:
            buffer (str): JSON string to write
        """
        try:
            # Parse JSON to validate and pretty-print if needed
            json_data = json.loads(buffer)

            # Write to JSONL format (one JSON object per line)
            with open(self.ocptv_file, "a", encoding="utf-8") as f:
                f.write(buffer.rstrip())
                f.write("\n")

            # Also log key information to the main logger
            self._log_ocptv_event(json_data)

        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON in OCP TV output: {e}")
            # Still write the raw buffer for debugging
            with open(self.ocptv_file, "a", encoding="utf-8") as f:
                f.write(f"# INVALID JSON: {buffer}\n")
        except Exception as e:
            self.logger.error(f"Error writing OCP TV output: {e}")

    def _log_ocptv_event(self, json_data: Dict[str, Any]) -> None:
        """
        Log key OCP TV events to the main logger for visibility.

        Args:
            json_data (dict): Parsed JSON data from OCP TV
        """
        try:
            # Log test run events
            if "testRunArtifact" in json_data:
                artifact = json_data["testRunArtifact"]
                if "testRunStart" in artifact:
                    start_info = artifact["testRunStart"]
                    self.logger.info(
                        f"🚀 Test Run Started: {start_info.get('name', 'Unknown')}"
                    )
                elif "testRunEnd" in artifact:
                    end_info = artifact["testRunEnd"]
                    status = end_info.get("status", "Unknown")
                    result = end_info.get("result", "Unknown")
                    self.logger.info(
                        f"✅ Test Run Ended: Status={status}, Result={result}"
                    )

            # Log test step events
            elif "testStepArtifact" in json_data:
                artifact = json_data["testStepArtifact"]
                step_id = artifact.get("testStepId", "Unknown")

                if "testStepStart" in artifact:
                    start_info = artifact["testStepStart"]
                    self.logger.info(
                        f"🔄 Test Step Started: {start_info.get('name', f'Step {step_id}')}"
                    )
                elif "testStepEnd" in artifact:
                    end_info = artifact["testStepEnd"]
                    status = end_info.get("status", "Unknown")
                    self.logger.info(
                        f"⏹️  Test Step Ended: Step {step_id}, Status={status}"
                    )
                elif "diagnosis" in artifact:
                    diagnosis = artifact["diagnosis"]
                    verdict = diagnosis.get("verdict", "Unknown")
                    diag_type = diagnosis.get("type", "Unknown")
                    if diag_type == "PASS":
                        self.logger.info(f"✅ Diagnosis PASS: {verdict}")
                    else:
                        self.logger.error(f"❌ Diagnosis FAIL: {verdict}")
                elif "measurement" in artifact:
                    measurement = artifact["measurement"]
                    name = measurement.get("name", "Unknown")
                    value = measurement.get("value", "Unknown")
                    unit = measurement.get("unit", "")
                    self.logger.debug(f"📊 Measurement: {name} = {value} {unit}")
                elif "error" in artifact:
                    error = artifact["error"]
                    msg = error.get("message", "Unknown error")
                    self.logger.error(f"🚨 Test Error: {msg}")

        except Exception as e:
            self.logger.debug(f"Error parsing OCP TV event for logging: {e}")
