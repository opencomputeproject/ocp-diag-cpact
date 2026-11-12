"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

===============================================================================
RedfishConnection is a REST-based connection class for interacting with Redfish-compliant
hardware management interfaces. It supports secure communication over HTTP/HTTPS and provides
methods for executing Redfish API calls using standard HTTP verbs.

Features:
- Establishes Redfish sessions using basic authentication.
- Supports GET, POST, PUT, PATCH, and DELETE operations.
- Automatically constructs base URLs from configuration and global settings.
- Verifies TLS certificates by default (configurable via verify_ssl / ca_bundle).
- Provides structured response output including status codes, headers, and JSON payloads.

Attributes:
    config (dict): Connection-specific configuration including host, port, and credentials.
    global_config (dict): Global settings including SSL preferences and default ports.
    session (requests.Session): Active HTTP session for Redfish communication.
    base_url (str): Constructed base URL for Redfish API calls.

Usage:
    Instantiate RedfishConnection with config and global_config.
    Call `connect()` to establish the session.
    Use `execute_command()` to perform Redfish API operations.
    Call `disconnect()` to close the session when done.
===============================================================================
"""

import os
import requests
from typing import Dict, Any, Union
from requests.adapters import HTTPAdapter
from requests.auth import HTTPBasicAuth

from cpact.system_connections.base_connection import ConnectionInterface
from cpact.system_connections.connection_config import (
    ConnectionConfig,
    RetryPolicy,
    parse_optional_bool,
)
from cpact.system_connections.retry import retry_call


class ServerHostnameAdapter(HTTPAdapter):
    """
    HTTPS adapter that verifies the certificate against ``server_hostname``
    instead of the URL host. Used when Redfish traffic goes through a local SSH
    tunnel (URL host is localhost) but the certificate belongs to the real BMC.
    """

    def __init__(self, server_hostname: str, **kwargs: Any) -> None:
        self.server_hostname = server_hostname
        super().__init__(**kwargs)

    def init_poolmanager(self, *args: Any, **kwargs: Any) -> None:
        kwargs["server_hostname"] = self.server_hostname
        kwargs["assert_hostname"] = self.server_hostname
        super().init_poolmanager(*args, **kwargs)


class RedfishConnection(ConnectionInterface):
    """Redfish API connection implementation"""

    def __init__(self, config: Dict[str, Any], global_config: Dict[str, Any]) -> None:
        """Initialize Redfish connection with config and global settings"""
        super().__init__(config)
        self.global_config = global_config
        self.conn_config = ConnectionConfig.from_dict(config)
        self.session = None
        self.base_url = None

    def connect(self) -> bool:
        """Establish Redfish connection (with configurable retry)."""
        try:
            host = self._get_host()
            port = self._get_redfish_port()
            use_ssl = self.global_config.get("Connection", {}).get("use_ssl", True)

            protocol = "https" if use_ssl else "http"
            self.base_url = f"{protocol}://{host}:{port}"

            self.session = requests.Session()
            self.session.verify = self._get_tls_verify()
            self._configure_session(self.session)

            username = self._get_username()
            password = self._get_password()

            if username and password:
                self.session.auth = HTTPBasicAuth(username, password)

            retry = RetryPolicy.from_config(self.global_config.get("Connection", {}))

            def _probe():
                response = self.session.get(
                    f"{self.base_url}/redfish/v1/", timeout=30
                )
                response.raise_for_status()
                return response

            retry_call(
                _probe,
                retries=retry.retry_count,
                delay=retry.retry_delay,
                logger=self.logger,
                description=f"Redfish connect to {host}:{port}",
            )
            self.logger.info(f"Redfish connection established to {host}:{port}")
            return True
        except Exception as e:
            self.logger.error(f"Redfish connection failed: {e}")
            if self.session:
                try:
                    self.session.close()
                except Exception:
                    pass
                self.session = None
            return False

    def health_check(self) -> bool:
        """Probe the service root; True only on a 2xx response."""
        if not self.is_connected():
            return False
        try:
            resp = self.session.get(f"{self.base_url}/redfish/v1/", timeout=10)
            return resp.ok
        except Exception as e:
            self.logger.warning(f"Redfish health check failed: {e}")
            return False

    def execute_command(self, command: str, **kwargs) -> Dict[str, Any]:
        """Execute a Redfish command (GET, POST, etc.)"""
        if not self.is_connected():
            raise ConnectionError("Redfish connection not established")

        try:
            method = kwargs.get("method", "GET").upper()
            endpoint = command  # For Redfish, command is typically an endpoint
            data = kwargs.get("data", None)

            url = f"{self.base_url}{endpoint}"

            if method == "GET":
                response = self.session.get(url, timeout=kwargs.get("timeout", 30))
            elif method == "POST":
                response = self.session.post(
                    url, json=data, timeout=kwargs.get("timeout", 30)
                )
            elif method == "PUT":
                response = self.session.put(
                    url, json=data, timeout=kwargs.get("timeout", 30)
                )
            elif method == "PATCH":
                response = self.session.patch(
                    url, json=data, timeout=kwargs.get("timeout", 30)
                )
            elif method == "DELETE":
                response = self.session.delete(url, timeout=kwargs.get("timeout", 30))
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            try:
                body = response.json() if response.content else {}
            except ValueError:
                body = {"raw": response.text}

            result = {
                "success": response.ok,
                "status_code": response.status_code,
                "response": body,
                "headers": dict(response.headers),
            }
            if not response.ok:
                result["error"] = f"HTTP {response.status_code} {response.reason or ''}".strip()
            return result
        except Exception as e:
            # e.response (when present) is a requests.Response, which has no
            # .get(); read its numeric .status_code attribute instead.
            resp = getattr(e, "response", None)
            status_code = getattr(resp, "status_code", -1) if resp is not None else -1
            return {
                "success": False,
                "error": str(e),
                "status_code": status_code,
            }

    def disconnect(self) -> None:
        """Close Redfish connection"""
        if self.session:
            self.session.close()
            self.session = None

    def is_connected(self) -> bool:
        """Check if Redfish connection is active"""
        return self.session is not None

    def _get_host(self) -> str:
        """Determine the host from config"""
        return self.conn_config.host

    def _get_tls_verify(self) -> Union[bool, str]:
        """
        Resolve the requests ``verify`` value for this connection.

        Per-section ``<prefix>_verify_ssl`` / ``<prefix>_ca_bundle`` override the
        global ``Connection.verify_ssl`` / ``Connection.ca_bundle``. Verification
        is on by default; a CA bundle path is returned when configured.
        """
        global_conn = self.global_config.get("Connection", {}) or {}
        verify = parse_optional_bool(self.conn_config.verify_ssl)
        if verify is None:
            verify = parse_optional_bool(global_conn.get("verify_ssl"))
        if verify is None:
            verify = True

        if not verify:
            self.logger.warning(
                f"TLS certificate verification is DISABLED for Redfish host "
                f"{self._get_host()} (verify_ssl=false). Credentials sent to this "
                "host can be intercepted; configure ca_bundle instead where possible."
            )
            return False

        ca_bundle = self.conn_config.ca_bundle or global_conn.get("ca_bundle", "")
        if ca_bundle:
            if not os.path.exists(ca_bundle):
                raise FileNotFoundError(f"Redfish ca_bundle not found: {ca_bundle}")
            return ca_bundle
        return True

    def _configure_session(self, session: requests.Session) -> None:
        """Hook for subclasses to customise the session before the first request."""

    def _get_redfish_port(self) -> int:
        """Determine the Redfish port from config or global settings"""
        if self.conn_config.prefix and f"{self.conn_config.prefix}_redfish_port" in self.config:
            return self.conn_config.redfish_port
        return self.global_config.get("Connection", {}).get("redfish_port", 443)

    def _get_username(self) -> str:
        """Determine the username from config"""
        return self.conn_config.username

    def _get_password(self) -> str:
        """Determine the password from config"""
        return self.conn_config.password
