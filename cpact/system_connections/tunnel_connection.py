"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.
"""

import time
import threading
from typing import Dict, Any

from sshtunnel import SSHTunnelForwarder
from system_connections.redfish_connection import RedfishConnection
from system_connections.ssh_connection import SSHConnection


class TunnelConnection(SSHConnection):
    """SSH Tunnel connection for NodeManager using sshtunnel"""
    
    def __init__(self, config: Dict[str, Any], tunnel_config: Dict[str, Any]):
        super().__init__(config)
        self.tunnel_config = tunnel_config
        self.ssh_tunnel = None
        self.redfish_tunnel = None
        self._tunnel_lock = threading.Lock()
    
    def connect(self) -> bool:
        """Establish SSH tunnel first, then SSH connection"""
        if self.config.get('nodemanager_tunnel'):
            if not self._create_tunnels():
                return False
            
            # Wait a moment for tunnels to establish
            time.sleep(1)
        
        return super().connect()
    
    def _create_tunnels(self) -> bool:
        """Create SSH and Redfish tunnels using sshtunnel"""
        try:
            tunnel_agent = self.tunnel_config.get('nodemanager_tunnel_agent', '')
            local_host = self.tunnel_config.get('nodemanager_tunnel_local_host', 'localhost')
            ssh_local_port = int(self.tunnel_config.get('nodemanager_tunnel_ssh_local_port', 2222))
            redfish_local_port = int(self.tunnel_config.get('nodemanager_tunnel_redfish_local_port', 8443))
            
            # Extract tunnel credentials (could be different from target credentials)
            tunnel_username = self.config.get('nodemanager_username', '')
            tunnel_password = self.config.get('nodemanager_password', '')
            
            # Create SSH tunnel
            self.ssh_tunnel = SSHTunnelForwarder(
                ssh_address_or_host=(tunnel_agent, 22),
                ssh_username=tunnel_username,
                ssh_password=tunnel_password,
                local_bind_address=(local_host, ssh_local_port),
                remote_bind_address=(self.config['nodemanager_host'], self.config['nodemanager_ssh_port']),
                set_keepalive=30
            )
            
            # Create Redfish tunnel
            self.redfish_tunnel = SSHTunnelForwarder(
                ssh_address_or_host=(tunnel_agent, 22),
                ssh_username=tunnel_username,
                ssh_password=tunnel_password,
                local_bind_address=(local_host, redfish_local_port),
                remote_bind_address=(self.config['nodemanager_host'], self.config['nodemanager_redfish_port']),
                set_keepalive=30
            )
            
            # Start tunnels
            with self._tunnel_lock:
                self.ssh_tunnel.start()
                self.redfish_tunnel.start()
            
            print(f"SSH Tunnel: {local_host}:{ssh_local_port} -> {self.config['nodemanager_host']}:{self.config['nodemanager_ssh_port']}")
            print(f"Redfish Tunnel: {local_host}:{redfish_local_port} -> {self.config['nodemanager_host']}:{self.config['nodemanager_redfish_port']}")
            
            return True
            
        except Exception as e:
            print(f"Failed to create tunnels: {e}")
            self._cleanup_tunnels()
            return False
    
    def _cleanup_tunnels(self):
        """Clean up tunnel connections"""
        with self._tunnel_lock:
            if self.ssh_tunnel:
                try:
                    self.ssh_tunnel.stop()
                except:
                    pass
                self.ssh_tunnel = None
            
            if self.redfish_tunnel:
                try:
                    self.redfish_tunnel.stop()
                except:
                    pass
                self.redfish_tunnel = None
    
    def _get_host(self) -> str:
        """Override to use tunneled localhost when tunnel is active"""
        if self.ssh_tunnel and self.ssh_tunnel.is_active:
            return self.tunnel_config.get('nodemanager_tunnel_local_host', 'localhost')
        return self.config.get('nodemanager_host', '')
    
    def _get_ssh_port(self) -> int:
        """Override to use local tunnel port when tunnel is active"""
        if self.ssh_tunnel and self.ssh_tunnel.is_active:
            return int(self.tunnel_config.get('nodemanager_tunnel_ssh_local_port', 2222))
        return self.config.get('nodemanager_ssh_port', 22)
    
    def get_tunnel_info(self) -> Dict[str, Any]:
        """Get information about active tunnels"""
        info = {
            'ssh_tunnel_active': self.ssh_tunnel.is_active if self.ssh_tunnel else False,
            'redfish_tunnel_active': self.redfish_tunnel.is_active if self.redfish_tunnel else False,
        }
        
        if self.ssh_tunnel and self.ssh_tunnel.is_active:
            info['ssh_local_bind_port'] = self.ssh_tunnel.local_bind_port
            info['ssh_local_bind_host'] = self.ssh_tunnel.local_bind_host
        
        if self.redfish_tunnel and self.redfish_tunnel.is_active:
            info['redfish_local_bind_port'] = self.redfish_tunnel.local_bind_port
            info['redfish_local_bind_host'] = self.redfish_tunnel.local_bind_host
        
        return info
    
    def disconnect(self):
        """Disconnect SSH connection and close tunnels"""
        super().disconnect()
        self._cleanup_tunnels()
    
    def is_connected(self) -> bool:
        """Check if both SSH connection and tunnels are active"""
        ssh_connected = super().is_connected()
        tunnels_active = True
        
        if self.config.get('nodemanager_tunnel'):
            tunnels_active = (
                self.ssh_tunnel and self.ssh_tunnel.is_active and
                self.redfish_tunnel and self.redfish_tunnel.is_active
            )
        
        return ssh_connected and tunnels_active


class TunneledRedfishConnection(RedfishConnection):
    """Redfish connection that can use SSH tunnel"""
    
    def __init__(self, config: Dict[str, Any], global_config: Dict[str, Any], tunnel_config: Dict[str, Any] = None):
        super().__init__(config, global_config)
        self.tunnel_config = tunnel_config or {}
        self.tunnel = None
        self._tunnel_lock = threading.Lock()
    
    def connect(self) -> bool:
        """Connect with optional tunnel support"""
        if self.config.get('nodemanager_tunnel') and self.tunnel_config:
            if not self._create_tunnel():
                return False
            time.sleep(1)  # Wait for tunnel to establish
        
        return super().connect()
    
    def _create_tunnel(self) -> bool:
        """Create Redfish tunnel"""
        try:
            tunnel_agent = self.tunnel_config.get('nodemanager_tunnel_agent', '')
            local_host = self.tunnel_config.get('nodemanager_tunnel_local_host', 'localhost')
            redfish_local_port = int(self.tunnel_config.get('nodemanager_tunnel_redfish_local_port', 8443))
            
            tunnel_username = self.config.get('nodemanager_username', '')
            tunnel_password = self.config.get('nodemanager_password', '')
            
            self.tunnel = SSHTunnelForwarder(
                ssh_address_or_host=(tunnel_agent, 22),
                ssh_username=tunnel_username,
                ssh_password=tunnel_password,
                local_bind_address=(local_host, redfish_local_port),
                remote_bind_address=(self.config['nodemanager_host'], self.config['nodemanager_redfish_port']),
                set_keepalive=30
            )
            
            with self._tunnel_lock:
                self.tunnel.start()
            
            print(f"Redfish Tunnel: {local_host}:{redfish_local_port} -> {self.config['nodemanager_host']}:{self.config['nodemanager_redfish_port']}")
            return True
            
        except Exception as e:
            print(f"Failed to create Redfish tunnel: {e}")
            return False
    
    def _get_host(self) -> str:
        """Override to use tunneled localhost when tunnel is active"""
        if self.tunnel and self.tunnel.is_active:
            return self.tunnel_config.get('nodemanager_tunnel_local_host', 'localhost')
        return super()._get_host()
    
    def _get_redfish_port(self) -> int:
        """Override to use local tunnel port when tunnel is active"""
        if self.tunnel and self.tunnel.is_active:
            return int(self.tunnel_config.get('nodemanager_tunnel_redfish_local_port', 8443))
        return super()._get_redfish_port()
    
    def disconnect(self):
        """Disconnect and cleanup tunnel"""
        super().disconnect()
        if self.tunnel:
            with self._tunnel_lock:
                try:
                    self.tunnel.stop()
                except:
                    pass
                self.tunnel = None
    
    def is_connected(self) -> bool:
        """Check if connection and tunnel are active"""
        base_connected = super().is_connected()
        tunnel_active = True
        
        if self.config.get('nodemanager_tunnel'):
            tunnel_active = self.tunnel and self.tunnel.is_active
        
        return base_connected and tunnel_active