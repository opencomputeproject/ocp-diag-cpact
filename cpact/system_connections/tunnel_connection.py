"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

===============================================================================
TunnelConnection and TunneledRedfishConnection provide secure, tunnel-enabled connection
interfaces for NodeManager operations using SSH and Redfish protocols. These classes extend
existing connection types to support dynamic port forwarding via `sshtunnel`, enabling access
to remote systems through intermediate agents.

Features:
- Establishes SSH and Redfish tunnels using `SSHTunnelForwarder`.
- Verifies the tunnel agent's SSH host key against known_hosts.
- Supports dynamic local port binding and keepalive settings.
- Integrates with existing SSHConnection and RedfishConnection classes.
- Automatically overrides host and port resolution when tunnels are active.
- Provides tunnel status and metadata for diagnostics.
- Ensures thread-safe tunnel creation and cleanup.

Classes:
    TunnelConnection:
        Extends SSHConnection to support SSH and Redfish tunneling.
        Manages tunnel lifecycle and overrides connection parameters.

    TunneledRedfishConnection:
        Extends RedfishConnection to support Redfish tunneling.
        Manages tunnel lifecycle and overrides host/port resolution.

Attributes:
    ssh_tunnel (SSHTunnelForwarder): Active SSH tunnel instance.
    redfish_tunnel (SSHTunnelForwarder): Active Redfish tunnel instance.
    tunnel_config (dict): Configuration for tunnel parameters.
    _tunnel_lock (threading.Lock): Ensures thread-safe tunnel operations.

Usage:
    Use TunnelConnection or TunneledRedfishConnection when NodeManager access requires
    intermediate tunneling. Configure tunnel parameters via `tunnel_config` and call
    `connect()` to establish secure access.
===============================================================================
"""

import time
import threading
from typing import Dict, Any

from sshtunnel import SSHTunnelForwarder
from cpact.system_connections.redfish_connection import (
    RedfishConnection,
    ServerHostnameAdapter,
)
from cpact.system_connections.ssh_connection import SSHConnection
from cpact.system_connections.ssh_client import load_known_host_key
from cpact.system_connections.connection_config import TunnelAgentConfig, RetryPolicy
from cpact.system_connections.retry import retry_call


class TunnelConnection(SSHConnection):
    """SSH Tunnel connection for NodeManager using sshtunnel"""

    def __init__(self, config: Dict[str, Any], connection_config: Dict[str, Any], tunnel_config: Dict[str, Any]) -> None:
        super().__init__(connection_config)
        self.connection_config = connection_config
        self.tunnel_config = tunnel_config
        self.ssh_tunnel = None
        self.redfish_tunnel = None
        self._tunnel_lock = threading.Lock()
        self.total_config = config  # Store the global configuration for tunnel agent access

    def connect(self) -> bool:
        """Establish SSH tunnel first, then SSH connection"""
        if self.connection_config.get("nodemanager_tunnel"):
            if not self._create_tunnels():
                return False

            # Wait a moment for tunnels to establish
            time.sleep(1)

        return super().connect()

    def _create_tunnels(self) -> bool:
        """Create SSH and Redfish tunnels using sshtunnel.

        Tunnel *agent* (jump host) credentials are resolved independently of
        the NodeManager target credentials via TunnelAgentConfig. This is the
        fix for the ``No password or public key available`` failure, which
        happened when the agent host/user/password could not be resolved and
        SSHTunnelForwarder was handed blanks.
        """
        agent = TunnelAgentConfig.from_config(self.tunnel_config, self.total_config)

        if not agent.valid:
            gaps = ", ".join(agent.missing())
            self.logger.error(
                "Cannot create tunnels: missing tunnel agent credentials "
                f"({gaps}). Provide tunnel_agent_host/username/password on the "
                "NodeManagerTunnel section, or a valid nodemanager_tunnel_agent "
                "pointing at a configured section."
            )
            return False

        target_host = self.connection_config["nodemanager_host"]
        target_ssh_port = self.connection_config["nodemanager_ssh_port"]
        target_redfish_port = self.connection_config["nodemanager_redfish_port"]

        retry = RetryPolicy.from_config(self.tunnel_config)

        def _build_and_start() -> bool:
            # A previous attempt may have started one tunnel before failing.
            self._cleanup_tunnels()
            self.ssh_tunnel = SSHTunnelForwarder(
                ssh_address_or_host=(agent.host, agent.ssh_port),
                ssh_host_key=host_key,
                ssh_username=agent.username,
                ssh_password=agent.password,
                local_bind_address=(agent.local_host, agent.ssh_local_port),
                remote_bind_address=(target_host, target_ssh_port),
                set_keepalive=agent.keepalive,
            )
            self.redfish_tunnel = SSHTunnelForwarder(
                ssh_address_or_host=(agent.host, agent.ssh_port),
                ssh_host_key=host_key,
                ssh_username=agent.username,
                ssh_password=agent.password,
                local_bind_address=(agent.local_host, agent.redfish_local_port),
                remote_bind_address=(target_host, target_redfish_port),
                set_keepalive=agent.keepalive,
            )
            with self._tunnel_lock:
                self.ssh_tunnel.start()
                self.redfish_tunnel.start()
            return True

        try:
            host_key = load_known_host_key(
                agent.host, agent.ssh_port, agent.known_hosts_file or None
            )
            retry_call(
                _build_and_start,
                retries=retry.retry_count,
                delay=retry.retry_delay,
                logger=self.logger,
                description=f"tunnel via agent {agent.host}:{agent.ssh_port}",
            )
            self.logger.info(
                f"SSH tunnel up: {agent.local_host}:{agent.ssh_local_port} -> "
                f"{target_host}:{target_ssh_port} (agent {agent.host}, {agent.source})"
            )
            self.logger.info(
                f"Redfish tunnel up: {agent.local_host}:{agent.redfish_local_port} -> "
                f"{target_host}:{target_redfish_port}"
            )
            return True
        except Exception as e:
            self.logger.error(f"Failed to create tunnels: {e}")
            self._cleanup_tunnels()
            return False

    def _cleanup_tunnels(self) -> None:
        """Clean up tunnel connections"""
        with self._tunnel_lock:
            if self.ssh_tunnel:
                try:
                    self.ssh_tunnel.stop()
                except Exception as e:
                    self.logger.warning(f"Error stopping SSH tunnel: {e}")
                self.ssh_tunnel = None

            if self.redfish_tunnel:
                try:
                    self.redfish_tunnel.stop()
                except Exception as e:
                    self.logger.warning(f"Error stopping Redfish tunnel: {e}")
                self.redfish_tunnel = None

    def _get_host(self) -> str:
        """Override to use tunneled localhost when tunnel is active"""
        if self.ssh_tunnel and self.ssh_tunnel.is_active:
            return self.tunnel_config.get("nodemanager_tunnel_local_host", "localhost")
        return self.connection_config.get("nodemanager_host", "")

    def _get_ssh_port(self) -> int:
        """Override to use local tunnel port when tunnel is active"""
        if self.ssh_tunnel and self.ssh_tunnel.is_active:
            return int(
                self.tunnel_config.get("nodemanager_tunnel_ssh_local_port", 2222)
            )
        return self.connection_config.get("nodemanager_ssh_port", 22)

    def get_tunnel_info(self) -> Dict[str, Any]:
        """Get information about active tunnels"""
        info = {
            "ssh_tunnel_active": (
                self.ssh_tunnel.is_active if self.ssh_tunnel else False
            ),
            "redfish_tunnel_active": (
                self.redfish_tunnel.is_active if self.redfish_tunnel else False
            ),
        }

        if self.ssh_tunnel and self.ssh_tunnel.is_active:
            info["ssh_local_bind_port"] = self.ssh_tunnel.local_bind_port
            info["ssh_local_bind_host"] = self.ssh_tunnel.local_bind_host

        if self.redfish_tunnel and self.redfish_tunnel.is_active:
            info["redfish_local_bind_port"] = self.redfish_tunnel.local_bind_port
            info["redfish_local_bind_host"] = self.redfish_tunnel.local_bind_host

        return info

    def disconnect(self) -> None:
        """Disconnect SSH connection and close tunnels"""
        super().disconnect()
        self._cleanup_tunnels()

    def is_connected(self) -> bool:
        """Check if both SSH connection and tunnels are active"""
        ssh_connected = super().is_connected()
        tunnels_active = True

        if self.connection_config.get("nodemanager_tunnel"):
            tunnels_active = (
                self.ssh_tunnel
                and self.ssh_tunnel.is_active
                and self.redfish_tunnel
                and self.redfish_tunnel.is_active
            )

        return ssh_connected and tunnels_active


class TunneledRedfishConnection(RedfishConnection):
    """Redfish connection that can use SSH tunnel"""

    def __init__(
        self,
        config: Dict[str, Any],
        global_config: Dict[str, Any],
        tunnel_config: Dict[str, Any] = None,
    ) -> None:
        super().__init__(config, global_config)
        self.tunnel_config = tunnel_config or {}
        self.global_config = global_config or {}
        self.tunnel = None
        self._tunnel_lock = threading.Lock()

    def connect(self) -> bool:
        """Connect with optional tunnel support"""
        if self.config.get("nodemanager_tunnel") and self.tunnel_config:
            if not self._create_tunnel():
                return False
            time.sleep(1)  # Wait for tunnel to establish

        return super().connect()

    def _create_tunnel(self) -> bool:
        """Create Redfish tunnel.

        Previously this passed the tunnel-agent *section name* (e.g.
        "RackManager") straight into SSHTunnelForwarder as if it were a
        hostname, and reused NodeManager credentials for the jump host. Both
        were bugs. We now resolve the real agent host/credentials the same way
        the SSH tunnel does.
        """
        agent = TunnelAgentConfig.from_config(self.tunnel_config, self.global_config)

        if not agent.valid:
            gaps = ", ".join(agent.missing())
            self.logger.error(
                f"Cannot create Redfish tunnel: missing tunnel agent credentials ({gaps})."
            )
            return False

        retry = RetryPolicy.from_config(self.tunnel_config)

        def _build_and_start() -> bool:
            self._stop_tunnel()
            self.tunnel = SSHTunnelForwarder(
                ssh_address_or_host=(agent.host, agent.ssh_port),
                ssh_host_key=host_key,
                ssh_username=agent.username,
                ssh_password=agent.password,
                local_bind_address=(agent.local_host, agent.redfish_local_port),
                remote_bind_address=(
                    self.config["nodemanager_host"],
                    self.config["nodemanager_redfish_port"],
                ),
                set_keepalive=agent.keepalive,
            )
            with self._tunnel_lock:
                self.tunnel.start()
            return True

        try:
            host_key = load_known_host_key(
                agent.host, agent.ssh_port, agent.known_hosts_file or None
            )
            retry_call(
                _build_and_start,
                retries=retry.retry_count,
                delay=retry.retry_delay,
                logger=self.logger,
                description=f"Redfish tunnel via agent {agent.host}:{agent.ssh_port}",
            )
            self.logger.info(
                f"Redfish tunnel up: {agent.local_host}:{agent.redfish_local_port} -> "
                f"{self.config['nodemanager_host']}:{self.config['nodemanager_redfish_port']}"
            )
            return True
        except Exception as e:
            self.logger.error(f"Failed to create Redfish tunnel: {e}")
            self._stop_tunnel()
            return False

    def _stop_tunnel(self) -> None:
        """Stop and forget the Redfish tunnel, if any."""
        with self._tunnel_lock:
            if self.tunnel:
                try:
                    self.tunnel.stop()
                except Exception as e:
                    self.logger.warning(f"Error stopping Redfish tunnel: {e}")
                self.tunnel = None

    def _get_host(self) -> str:
        """Override to use tunneled localhost when tunnel is active"""
        if self.tunnel and self.tunnel.is_active:
            return self.tunnel_config.get("nodemanager_tunnel_local_host", "localhost")
        return super()._get_host()

    def _get_redfish_port(self) -> int:
        """Override to use local tunnel port when tunnel is active"""
        if self.tunnel and self.tunnel.is_active:
            return int(
                self.tunnel_config.get("nodemanager_tunnel_redfish_local_port", 8443)
            )
        return super()._get_redfish_port()

    def _configure_session(self, session) -> None:
        """Verify the BMC certificate against its real hostname, not the tunnel's localhost."""
        if self.tunnel and self.tunnel.is_active and session.verify is not False:
            session.mount(
                "https://", ServerHostnameAdapter(self.config["nodemanager_host"])
            )

    def disconnect(self) -> None:
        """Disconnect and cleanup tunnel"""
        super().disconnect()
        self._stop_tunnel()

    def is_connected(self) -> bool:
        """Check if connection and tunnel are active"""
        base_connected = super().is_connected()
        tunnel_active = True

        if self.config.get("nodemanager_tunnel"):
            tunnel_active = self.tunnel and self.tunnel.is_active

        return base_connected and tunnel_active
