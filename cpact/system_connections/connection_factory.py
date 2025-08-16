"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.
"""

import threading
from typing import Dict, Any

from system_connections.base_connection import ConnectionInterface
from system_connections.local_connection import LocalConnection
from system_connections.ssh_connection import SSHConnection
from system_connections.redfish_connection import RedfishConnection
from system_connections.tunnel_connection import TunneledRedfishConnection
from system_connections.tunnel_connection import TunnelConnection

class ConnectionFactory:
    """Factory class to create appropriate connection objects"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, config: Dict[str, Any] = None):
        """Implement Singleton pattern (optional - can be disabled)"""
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(ConnectionFactory, cls).__new__(cls)
        return cls._instance
    
    def __init__(self, config: Dict[str, Any] = None):
        # Only initialize once
        if not hasattr(self, 'initialized'):
            self.config = config or {}
            self.connections = {}
            self.initialized = True
        elif config:
            # Update config if provided
            self.config.update(config)
    
    @classmethod
    def get_instance(cls, config: Dict[str, Any] = None) -> 'ConnectionFactory':
        """Get singleton instance"""
        return cls(config)
    
    @classmethod
    def reset_instance(cls):
        """Reset singleton instance (useful for testing)"""
        with cls._lock:
            if cls._instance:
                cls._instance.close_all_connections()
            cls._instance = None
    
    def create_connection(self, connection_name: str, connection_type: str) -> ConnectionInterface:
        """
        Create a connection based on connection name and type
        
        Args:
            connection_name: Name of the connection (Inband, RackManager, NodeManager)
            connection_type: Type of connection (ssh, redfish, local)
        
        Returns:
            ConnectionInterface: Appropriate connection object
        """
        # if connection_name not in self.config and connection_name != 'local':
        #     print(f"Connection '{connection_name}' not found in configuration")
        #     raise ValueError(f"Connection '{connection_name}' not found in configuration")
        connection_config = self.config.get(connection_name, {})
        
        # Create connection based on type
        if connection_type.lower() == 'ssh':
            if connection_name == 'NodeManager' and connection_config.get('nodemanager_tunnel'):
                tunnel_config = self.config.get('NodeManagerTunnel', {})
                return TunnelConnection(connection_config, tunnel_config)
            else:
                return SSHConnection(connection_config)
        
        elif connection_type.lower() == 'redfish':
            if connection_name == 'NodeManager' and connection_config.get('nodemanager_tunnel'):
                tunnel_config = self.config.get('NodeManagerTunnel', {})
                return TunneledRedfishConnection(connection_config, self.config, tunnel_config)
            else:
                return RedfishConnection(connection_config, self.config)
        
        elif connection_name.lower() == 'local':
            return LocalConnection(connection_config)
        
        else:
            raise ValueError(f"Unsupported connection type: {connection_type}")
    
    def get_connection(self, connection_name: str, connection_type: str) -> ConnectionInterface:
        """
        Get or create a connection (singleton pattern for each connection+type combo)
        """
        key = f"{connection_name}_{connection_type}"
        
        if key not in self.connections:
            self.connections[key] = self.create_connection(connection_name, connection_type)
        
        return self.connections[key]
    
    def close_all_connections(self):
        """Close all active connections"""
        for connection in self.connections.values():
            connection.disconnect()
        self.connections.clear()
        print("All connections closed.")