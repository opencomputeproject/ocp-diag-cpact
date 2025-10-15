"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

===============================================================================
ConnectionInterface defines a standardized interface for all connection types used in
automated infrastructure and test environments. It serves as the base class for concrete
implementations such as SSH, Redfish, Local, and tunneled connections.

Features:
- Enforces a consistent API for connection lifecycle and command execution.
- Supports extensibility for various transport protocols.
- Integrates with centralized logging via TestLogger.
- Provides abstract methods for connect, disconnect, command execution, and status checks.

Classes:
    ConnectionInterface:
        Abstract base class for all connection implementations.
        Must be subclassed with concrete definitions for connection behavior.

Usage:
    Subclass ConnectionInterface to implement specific connection logic.
    Override all abstract methods to define connection handling and command execution.
    Use `TestLogger` for consistent logging across connection types.
===============================================================================
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Union

from utils.logger_utils import TestLogger


class ConnectionInterface(ABC):
    """Abstract base class for all connection types"""

    def __init__(self, config: Dict[str, Any]):
        """
        Initializes the connection with given configuration.
        Args:
            config (Dict[str, Any]): Configuration parameters for the connection.
        Returns:
            None
        """
        self.config = config
        self.connection = None
        self.logger = TestLogger().get_logger()

    @abstractmethod
    def connect(self) -> bool:
        """Establish connection"""
        pass

    @abstractmethod
    def execute_command(self, command: str, **kwargs) -> Dict[str, Any]:
        """Execute command and return result"""
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Close connection"""
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if connection is active"""
        pass
