"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

===============================================================================
ConnectionFactory is a centralized factory class for creating and managing connection objects
used in automated infrastructure and test environments. It supports multiple connection types
including SSH, Redfish, local execution, and tunneled variants, and implements a singleton
pattern to ensure consistent connection reuse across the application.

Features:
- Dynamically creates connections based on name and type.
- Supports SSH, Redfish, Local, and tunneled NodeManager connections.
- Implements singleton pattern for factory instance and connection reuse.
- Provides thread-safe access and lifecycle management.
- Allows resetting and cleanup of all active connections.

Classes:
    ConnectionFactory:
        Manages creation and caching of connection instances.
        Supports configuration injection and tunnel-aware connection logic.

Supported Connection Types:
    - SSHConnection
    - RedfishConnection
    - LocalConnection
    - TunnelConnection (SSH with tunnel)
    - TunneledRedfishConnection (Redfish with tunnel)

Usage:
    Use `ConnectionFactory.get_instance(config)` to initialize or retrieve the factory.
    Call `get_connection(name, type)` to retrieve or create a connection.
    Use `reset_instance()` or `close_all_connections()` to clean up resources.
===============================================================================
"""

import threading
from typing import Dict, Any

from cpact.system_connections.base_connection import ConnectionInterface
from cpact.system_connections.local_connection import LocalConnection
from cpact.system_connections.ssh_connection import SSHConnection
from cpact.system_connections.redfish_connection import RedfishConnection
from cpact.system_connections.tunnel_connection import TunneledRedfishConnection
from cpact.system_connections.tunnel_connection import TunnelConnection


class ConnectionFactory:
    """Factory class to create appropriate connection objects"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, config: Dict[str, Any] = None) -> "ConnectionFactory":
        """Implement Singleton pattern (optional - can be disabled)"""
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(ConnectionFactory, cls).__new__(cls)
        return cls._instance

    def __init__(self, config: Dict[str, Any] = None) -> None:
        """Initialize the factory with optional config (only once)"""
        # Only initialize once
        if not hasattr(self, "initialized"):
            self.config = config or {}
            self.connections = {}
            self.initialized = True
        elif config:
            # Update config if provided
            self.config.update(config)

    @classmethod
    def get_instance(cls, config: Dict[str, Any] = None) -> "ConnectionFactory":
        """Get singleton instance"""
        return cls(config)

    @classmethod
    def reset_instance(cls):
        """Reset singleton instance (useful for testing)"""
        with cls._lock:
            if cls._instance:
                cls._instance.close_all_connections()
            cls._instance = None

    # Registry mapping a *resolved* type key -> factory callable. This replaces
    # the previous nested if/elif blocks. Adding a new connection type is now a
    # one-line registry entry rather than another branch (Open/Closed).
    def _build_registry(self):
        return {
            "ssh": lambda name, cfg: SSHConnection(cfg),
            "redfish": lambda name, cfg: RedfishConnection(cfg, self.config),
            "local": lambda name, cfg: LocalConnection(cfg),
            "tunneled_ssh": lambda name, cfg: TunnelConnection(
                self.config, cfg, self.config.get("NodeManagerTunnel", {})
            ),
            "tunneled_redfish": lambda name, cfg: TunneledRedfishConnection(
                cfg, self.config, self.config.get("NodeManagerTunnel", {})
            ),
        }

    def _resolve_type_key(
        self, connection_name: str, connection_type: str, connection_config: Dict
    ) -> str:
        """
        Map (name, type, config) to a registry key, handling the one real
        special case: a tunneled NodeManager.
        """
        ctype = connection_type.lower()
        if connection_name.lower() == "local" or ctype == "local":
            return "local"

        is_tunneled = connection_name == "NodeManager" and connection_config.get(
            "nodemanager_tunnel"
        )
        if ctype == "ssh":
            return "tunneled_ssh" if is_tunneled else "ssh"
        if ctype == "redfish":
            return "tunneled_redfish" if is_tunneled else "redfish"
        raise ValueError(f"Unsupported connection type: {connection_type}")

    def create_connection(
        self, connection_name: str, connection_type: str
    ) -> ConnectionInterface:
        """
        Create a connection based on connection name and type.

        Args:
            connection_name: Name of the connection (Inband, RackManager, NodeManager, local)
            connection_type: Type of connection (ssh, redfish, local)

        Returns:
            ConnectionInterface: Appropriate connection object
        """
        connection_config = self.config.get(connection_name, {})
        registry = self._build_registry()
        type_key = self._resolve_type_key(
            connection_name, connection_type, connection_config
        )
        factory = registry.get(type_key)
        if factory is None:
            raise ValueError(f"Unsupported connection type: {connection_type}")
        return factory(connection_name, connection_config)

    def get_connection(
        self, connection_name: str, connection_type: str
    ) -> ConnectionInterface:
        """
        Get or create a connection (cached per connection+type combo).

        Thread-safe: previously two threads could both miss the cache and each
        create a connection, leaking one. The double-checked lock fixes that.
        """
        key = f"{connection_name}_{connection_type}"

        conn = self.connections.get(key)
        if conn is not None:
            return conn

        with self._lock:
            conn = self.connections.get(key)
            if conn is None:
                conn = self.create_connection(connection_name, connection_type)
                self.connections[key] = conn
            return conn

    def close_all_connections(self) -> None:
        """Close all active connections"""
        with self._lock:
            connections = list(self.connections.values())
            self.connections.clear()
        for connection in connections:
            try:
                connection.disconnect()
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    # Backward-compatible static facade.
    #
    # Older CPACT consumers drive the factory through these module-level
    # class methods rather than the instance API. They are thin wrappers over
    # the singleton so both styles keep working. New code should prefer the
    # instance API (get_instance(config).get_connection(...)).
    # ------------------------------------------------------------------ #
    @classmethod
    def initialize(cls, config: Dict[str, Any] = None) -> "ConnectionFactory":
        """Initialize (or update) the singleton factory with a config."""
        return cls.get_instance(config)

    @classmethod
    def get_connections(cls) -> Dict[str, ConnectionInterface]:
        """Return the live map of cached connections for the singleton."""
        return cls.get_instance().connections

    @classmethod
    def execute_command(
        cls,
        connections: Dict[str, ConnectionInterface],
        connection_name: str,
        connection_type: str,
        command: str,
        **kwargs,
    ):
        """
        Execute a command on the named connection, creating/reusing it as needed.

        ``connections`` is accepted for signature compatibility with the legacy
        API; the singleton's own cache is authoritative.
        """
        factory = cls.get_instance()
        connection = factory.get_connection(connection_name, connection_type)
        if not connection.is_connected():
            connection.connect()
        return connection.execute_command(command, **kwargs)

    @classmethod
    def disconnect_all(cls, connections: Dict[str, ConnectionInterface] = None) -> None:
        """Disconnect every cached connection on the singleton."""
        cls.get_instance().close_all_connections()
