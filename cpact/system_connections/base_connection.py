"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Union

from utils.logger_utils import TestLogger

class ConnectionInterface(ABC):
    """Abstract base class for all connection types"""
    
    def __init__(self, config: Dict[str, Any]):
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
    def disconnect(self):
        """Close connection"""
        pass
    
    @abstractmethod
    def is_connected(self) -> bool:
        """Check if connection is active"""
        pass