"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

===============================================================================
ConnectionDiscovery is a utility class for identifying and validating all possible
connection configurations defined in a system. It integrates with the ConnectionFactory
to dynamically test SSH, Redfish, and local connections, including tunnel-based variants.

Features:
- Discovers valid connection name/type combinations from configuration.
- Validates connection readiness and command execution.
- Supports SSH, Redfish, and local connection types.
- Provides detailed test results including timing, status, and error messages.
- Prints formatted connection test summaries and exports results to CSV.

Classes:
    ConnectionDiscovery:
        Uses a ConnectionFactory to discover and test all configured connections.
        Supports tunnel-aware logic for NodeManager connections.

Usage:
    Instantiate ConnectionDiscovery with a ConnectionFactory.
    Call `discover_all_connections()` to list valid combinations.
    Use `test_all_connections()` to validate connectivity and command execution.
    Use `print_connection_table()` to display results.
    Use `export_results_to_csv()` to save results for reporting.
===============================================================================
"""
import time
from typing import Dict, Any, List

from system_connections.connection_factory import ConnectionFactory
from system_connections.base_connection import ConnectionInterface


class ConnectionDiscovery:
    """Discover and test all possible connections from configuration"""

    def __init__(self, factory: ConnectionFactory) -> None:
        """
        Initialize with a ConnectionFactory instance.
        Args: factory (ConnectionFactory): The factory to create connections.
        Returns: None
        """
        self.factory = factory
        self.config = factory.config

    def discover_all_connections(self) -> Dict[str, Any]:
        """Discover all possible connections from configuration"""
        discovered_connections = []

        # Get available connections and connection types from config
        connection_config = self.config.get("Connection", {})
        available_connections = connection_config.get("connections", [])
        available_types = connection_config.get("connection_types", [])

        # Also add 'local' type as it's always available
        if "local" not in available_types:
            available_types.append("local")

        # Generate all possible combinations
        for connection_name in available_connections:
            if connection_name in self.config:
                conn_config = self.config[connection_name]

                for conn_type in available_types:
                    # Check if this combination makes sense
                    if self._is_valid_combination(
                        connection_name, conn_type, conn_config
                    ):
                        discovered_connections.append(
                            {
                                "connection_name": connection_name,
                                "connection_type": conn_type,
                                "config_available": True,
                                "description": self._get_connection_description(
                                    connection_name, conn_type, conn_config
                                ),
                            }
                        )

        return {
            "total_combinations": len(discovered_connections),
            "connections": discovered_connections,
            "available_connection_names": available_connections,
            "available_connection_types": available_types,
        }

    def _is_valid_combination(
        self, connection_name: str, conn_type: str, conn_config: Dict
    ) -> bool:
        """Check if a connection name + type combination is valid"""

        # Local connections are always valid
        if conn_type == "local":
            return True

        # SSH connections need SSH-related config
        if conn_type == "ssh":
            ssh_indicators = [
                f"{connection_name.lower()}_host",
                f"{connection_name.lower()}_ssh_port",
                f"{connection_name.lower()}_username",
            ]
            return any(indicator in conn_config for indicator in ssh_indicators)

        # Redfish connections need Redfish-related config
        if conn_type == "redfish":
            redfish_indicators = [
                f"{connection_name.lower()}_host",
                f"{connection_name.lower()}_redfish_port",
            ]
            return any(indicator in conn_config for indicator in redfish_indicators)

        return False

    def _get_connection_description(
        self, connection_name: str, conn_type: str, conn_config: Dict
    ) -> str:
        """Generate a description for the connection"""
        if conn_type == "local":
            return f"Local system commands via {connection_name}"

        # Try to get host information
        host_key = f"{connection_name.lower()}_host"
        host = conn_config.get(host_key, "unknown")

        if conn_type == "ssh":
            port_key = f"{connection_name.lower()}_ssh_port"
            port = conn_config.get(port_key, 22)
            tunnel_info = ""
            if connection_name == "NodeManager" and conn_config.get(
                "nodemanager_tunnel"
            ):
                tunnel_info = " (via SSH tunnel)"
            return f"SSH to {host}:{port}{tunnel_info}"

        elif conn_type == "redfish":
            port_key = f"{connection_name.lower()}_redfish_port"
            port = conn_config.get(port_key, 443)
            tunnel_info = ""
            if connection_name == "NodeManager" and conn_config.get(
                "nodemanager_tunnel"
            ):
                tunnel_info = " (via SSH tunnel)"
            return f"Redfish API to {host}:{port}{tunnel_info}"

        return f"{conn_type.upper()} connection to {connection_name}"

    def test_all_connections(self, timeout: int = 10) -> List[Dict[str, Any]]:
        """Test connectivity for all discovered connections"""
        discovery_result = self.discover_all_connections()
        test_results = []

        print(
            f"Testing {discovery_result['total_combinations']} connection combinations..."
        )

        for i, conn_info in enumerate(discovery_result["connections"], 1):
            connection_name = conn_info["connection_name"]
            connection_type = conn_info["connection_type"]

            print(
                f"Testing {i}/{discovery_result['total_combinations']}: {connection_name} ({connection_type})"
            )

            # Test the connection
            test_result = self._test_single_connection(
                connection_name, connection_type, conn_info["description"], timeout
            )

            test_results.append(test_result)

        return test_results

    def _test_single_connection(
        self, connection_name: str, connection_type: str, description: str, timeout: int
    ) -> Dict[str, Any]:
        """Test a single connection"""
        start_time = time.time()

        try:
            # Create connection
            connection = self.factory.create_connection(
                connection_name, connection_type
            )

            # Test connection
            connect_success = connection.connect()
            connect_time = time.time() - start_time

            if not connect_success:
                connection.disconnect()
                return {
                    "connection_name": connection_name,
                    "connection_type": connection_type,
                    "description": description,
                    "status": "FAILED",
                    "error": "Connection failed",
                    "connect_time": connect_time,
                    "command_time": None,
                    "total_time": connect_time,
                    "details": "Unable to establish connection",
                }

            # Test command execution
            cmd_start_time = time.time()
            command_result = self._execute_test_command(
                connection, connection_type, timeout
            )
            command_time = time.time() - cmd_start_time

            total_time = time.time() - start_time

            # Disconnect
            connection.disconnect()

            if command_result["success"]:
                return {
                    "connection_name": connection_name,
                    "connection_type": connection_type,
                    "description": description,
                    "status": "SUCCESS",
                    "error": None,
                    "connect_time": connect_time,
                    "command_time": command_time,
                    "total_time": total_time,
                    "details": f"Command output: {command_result.get('output', '')[:50]}...",
                }
            else:
                return {
                    "connection_name": connection_name,
                    "connection_type": connection_type,
                    "description": description,
                    "status": "PARTIAL",
                    "error": command_result.get("error", "Command execution failed"),
                    "connect_time": connect_time,
                    "command_time": command_time,
                    "total_time": total_time,
                    "details": "Connection successful but command failed",
                }

        except Exception as e:
            total_time = time.time() - start_time
            return {
                "connection_name": connection_name,
                "connection_type": connection_type,
                "description": description,
                "status": "ERROR",
                "error": str(e),
                "connect_time": None,
                "command_time": None,
                "total_time": total_time,
                "details": f"Exception during testing: {type(e).__name__}",
            }

    def _execute_test_command(
        self, connection: ConnectionInterface, connection_type: str, timeout: int
    ) -> Dict[str, Any]:
        """Execute appropriate test command based on connection type"""
        try:
            if connection_type == "ssh":
                result = connection.execute_command(
                    'echo "SSH test successful"', timeout=timeout
                )
                return {
                    "success": result.get("success", False),
                    "output": result.get("stdout", ""),
                    "error": result.get("stderr", "") or result.get("error", ""),
                }

            elif connection_type == "redfish":
                result = connection.execute_command("/redfish/v1/", timeout=timeout)
                return {
                    "success": result.get("success", False),
                    "output": f"HTTP {result.get('status_code', 'unknown')}",
                    "error": result.get("error", ""),
                }

            elif connection_type == "local":
                result = connection.execute_command(
                    'echo "Local test successful"', shell=True, timeout=timeout
                )
                return {
                    "success": result.get("success", False),
                    "output": result.get("stdout", ""),
                    "error": result.get("stderr", "") or result.get("error", ""),
                }

            else:
                return {
                    "success": False,
                    "output": "",
                    "error": f"Unknown connection type: {connection_type}",
                }

        except Exception as e:
            return {"success": False, "output": "", "error": str(e)}

    def print_connection_table(self, test_results: List[Dict[str, Any]]) -> None:
        """Print connection test results in a formatted table"""

        # Print header
        print("\n" + "=" * 120)
        print(f"{'CONNECTION TEST RESULTS':^120}")
        print("=" * 120)

        # Table header
        header = f"{'Connection':<15} {'Type':<8} {'Status':<8} {'Connect':<8} {'Command':<8} {'Total':<8} {'Description':<35} {'Details':<25}"
        print(header)
        print("-" * 120)

        # Sort results by status (SUCCESS, PARTIAL, FAILED, ERROR)
        status_order = {"SUCCESS": 1, "PARTIAL": 2, "FAILED": 3, "ERROR": 4}
        sorted_results = sorted(
            test_results, key=lambda x: status_order.get(x["status"], 5)
        )

        # Print results
        for result in sorted_results:
            connection = result["connection_name"][:14]
            conn_type = result["connection_type"][:7]
            status = result["status"][:7]

            # Format timing
            connect_time = (
                f"{result['connect_time']:.2f}s" if result["connect_time"] else "N/A"
            )
            command_time = (
                f"{result['command_time']:.2f}s" if result["command_time"] else "N/A"
            )
            total_time = (
                f"{result['total_time']:.2f}s" if result["total_time"] else "N/A"
            )

            description = result["description"][:34]
            details = result["details"][:24] if result["details"] else ""

            # Color coding for status
            status_symbol = {
                "SUCCESS": "✅",
                "PARTIAL": "⚠️ ",
                "FAILED": "❌",
                "ERROR": "💥",
            }.get(status, "❓")

            row = f"{connection:<15} {conn_type:<8} {status_symbol}{status:<7} {connect_time:<8} {command_time:<8} {total_time:<8} {description:<35} {details:<25}"
            print(row)

        # Print summary
        print("-" * 120)

        # Calculate statistics
        total_tests = len(test_results)
        successful = len([r for r in test_results if r["status"] == "SUCCESS"])
        partial = len([r for r in test_results if r["status"] == "PARTIAL"])
        failed = len([r for r in test_results if r["status"] == "FAILED"])
        errors = len([r for r in test_results if r["status"] == "ERROR"])

        print(
            f"SUMMARY: Total: {total_tests} | ✅ Success: {successful} | ⚠️  Partial: {partial} | ❌ Failed: {failed} | 💥 Error: {errors}"
        )

        # Success rate
        success_rate = (successful / total_tests * 100) if total_tests > 0 else 0
        print(f"SUCCESS RATE: {success_rate:.1f}%")
        print("=" * 120)

    def export_results_to_csv(
        self,
        test_results: List[Dict[str, Any]],
        filename: str = "connection_test_results.csv",
    ) -> bool:
        """Export test results to CSV file"""
        try:
            import csv

            with open(filename, "w", newline="", encoding="utf-8") as csvfile:
                fieldnames = [
                    "connection_name",
                    "connection_type",
                    "status",
                    "description",
                    "connect_time",
                    "command_time",
                    "total_time",
                    "error",
                    "details",
                ]
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

                writer.writeheader()
                for result in test_results:
                    writer.writerow(result)

            print(f"\n📄 Results exported to: {filename}")
            return True

        except Exception as e:
            print(f"❌ Failed to export CSV: {e}")
            return False
