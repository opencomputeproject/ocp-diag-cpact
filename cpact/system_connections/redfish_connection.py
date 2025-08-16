"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.
"""

import requests
from typing import Dict, Any
from requests.auth import HTTPBasicAuth

from system_connections.base_connection import ConnectionInterface

class RedfishConnection(ConnectionInterface):
    """Redfish API connection implementation"""
    
    def __init__(self, config: Dict[str, Any], global_config: Dict[str, Any]):
        super().__init__(config)
        self.global_config = global_config
        self.session = None
        self.base_url = None
    
    def connect(self) -> bool:
        try:
            host = self._get_host()
            port = self._get_redfish_port()
            use_ssl = self.global_config.get('Connection', {}).get('use_ssl', True)
            
            protocol = 'https' if use_ssl else 'http'
            self.base_url = f"{protocol}://{host}:{port}"
            
            self.session = requests.Session()
            self.session.verify = False  # For development - use proper certs in production
            
            username = self._get_username()
            password = self._get_password()
            
            if username and password:
                self.session.auth = HTTPBasicAuth(username, password)
            
            # Test connection with a simple GET to /redfish/v1/
            response = self.session.get(f"{self.base_url}/redfish/v1/", timeout=30)
            response.raise_for_status()
            
            return True
        except Exception as e:
            print(f"Redfish connection failed: {e}")
            return False
    
    def execute_command(self, command: str, **kwargs) -> Dict[str, Any]:
        if not self.is_connected():
            raise ConnectionError("Redfish connection not established")
        
        try:
            method = kwargs.get('method', 'GET').upper()
            endpoint = command  # For Redfish, command is typically an endpoint
            data = kwargs.get('data', None)
            
            url = f"{self.base_url}{endpoint}"
            
            if method == 'GET':
                response = self.session.get(url, timeout=kwargs.get('timeout', 30))
            elif method == 'POST':
                response = self.session.post(url, json=data, timeout=kwargs.get('timeout', 30))
            elif method == 'PUT':
                response = self.session.put(url, json=data, timeout=kwargs.get('timeout', 30))
            elif method == 'PATCH':
                response = self.session.patch(url, json=data, timeout=kwargs.get('timeout', 30))
            elif method == 'DELETE':
                response = self.session.delete(url, timeout=kwargs.get('timeout', 30))
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            return {
                'success': True,
                'status_code': response.status_code,
                'response': response.json() if response.content else {},
                'headers': dict(response.headers)
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'status_code': getattr(e, 'response', {}).get('status_code', -1)
            }
    
    def disconnect(self):
        if self.session:
            self.session.close()
            self.session = None
    
    def is_connected(self) -> bool:
        return self.session is not None
    
    def _get_host(self) -> str:
        if 'rackmanager_host' in self.config:
            return self.config['rackmanager_host']
        elif 'nodemanager_host' in self.config:
            return self.config['nodemanager_host']
        return ''
    
    def _get_redfish_port(self) -> int:
        if 'rackmanager_redfish_port' in self.config:
            return self.config['rackmanager_redfish_port']
        elif 'nodemanager_redfish_port' in self.config:
            return self.config['nodemanager_redfish_port']
        return self.global_config.get('Connection', {}).get('redfish_port', 443)
    
    def _get_username(self) -> str:
        if 'rackmanager_username' in self.config:
            return self.config['rackmanager_username']
        elif 'nodemanager_username' in self.config:
            return self.config['nodemanager_username']
        return ''
    
    def _get_password(self) -> str:
        if 'rackmanager_password' in self.config:
            return self.config['rackmanager_password']
        elif 'nodemanager_password' in self.config:
            return self.config['nodemanager_password']
        return ''
