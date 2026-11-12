"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

===============================================================================
Connection discovery for the CPACT CLI (--discover_connections): tests every
configured connection combination and summarises the results.

Extracted from cpact/main.py; cpact.main re-exports these names.
===============================================================================
"""

from collections import defaultdict
from typing import Any, Dict, List

from cpact.system_connections.connection_discovery import ConnectionDiscovery
from cpact.system_connections.connection_factory import ConnectionFactory


def discover_and_test_connections(
    config: Dict[str, Any], timeout: int = 10, export_csv: bool = False
) -> Dict[str, Any]:
    """
    Discover and test all connections from config.

    Args:
        config: Connection configuration.
        timeout: Timeout for connection tests in seconds.
        export_csv: Whether to export results to CSV.

    Returns:
        Dict containing discovery info, test results, and statistics.
    """
    print("🔍 DISCOVERING ALL POSSIBLE CONNECTIONS...")

    factory = ConnectionFactory.initialize(config)
    discovery = ConnectionDiscovery(factory)

    # Discover all connections
    discovery_result = discovery.discover_all_connections()
    print(
        f"📊 Found {discovery_result['total_combinations']} possible connection combinations:"
    )
    print(
        f"   • Connection Names: {', '.join(discovery_result['available_connection_names'])}"
    )
    print(
        f"   • Connection Types: {', '.join(discovery_result['available_connection_types'])}"
    )

    # Test all connections
    print(f"\n🧪 TESTING CONNECTIVITY (timeout: {timeout}s per test)...")
    test_results = discovery.test_all_connections(timeout=timeout)

    # Print results table (keep behavior)
    discovery.print_connection_table(test_results)

    # Export to CSV if requested
    if export_csv:
        discovery.export_results_to_csv(test_results)

    # Calculate detailed statistics
    stats = calculate_connection_statistics(test_results)

    # Clean up
    factory.close_all_connections()

    return {
        "discovery": discovery_result,
        "test_results": test_results,
        "statistics": stats,
    }


def calculate_connection_statistics(
    test_results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Calculate detailed statistics from test results.

    Args:
        test_results: List of connection test result dicts containing at least
                      'status', 'connection_type', 'connection_name', and optionally 'total_time'.

    Returns:
        Dictionary with summary counts, breakdowns by type and name, and timing aggregates.
    """
    if not test_results:
        return {}

    total = len(test_results)
    success_count = sum(1 for r in test_results if r.get("status") == "SUCCESS")
    partial_count = sum(1 for r in test_results if r.get("status") == "PARTIAL")
    failed_count = sum(1 for r in test_results if r.get("status") == "FAILED")
    error_count = sum(1 for r in test_results if r.get("status") == "ERROR")

    # Stats by connection type
    type_stats: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {"total": 0, "success": 0, "failed": 0}
    )
    for r in test_results:
        t = r.get("connection_type", "UNKNOWN")
        type_stats[t]["total"] += 1
        if r.get("status") == "SUCCESS":
            type_stats[t]["success"] += 1
        else:
            type_stats[t]["failed"] += 1

    # Stats by connection name
    name_stats: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {"total": 0, "success": 0, "failed": 0}
    )
    for r in test_results:
        n = r.get("connection_name", "UNKNOWN")
        name_stats[n]["total"] += 1
        if r.get("status") == "SUCCESS":
            name_stats[n]["success"] += 1
        else:
            name_stats[n]["failed"] += 1

    # Timing stats for successful results with numeric total_time
    successful_times = [
        float(r["total_time"])
        for r in test_results
        if r.get("status") == "SUCCESS"
        and isinstance(r.get("total_time"), (int, float))
    ]
    if successful_times:
        avg_time = sum(successful_times) / len(successful_times)
        min_time = min(successful_times)
        max_time = max(successful_times)
    else:
        avg_time = min_time = max_time = 0.0

    return {
        "summary": {
            "total_tests": total,
            "success_count": success_count,
            "partial_count": partial_count,
            "failed_count": failed_count,
            "error_count": error_count,
            "success_rate": (success_count / total * 100.0) if total > 0 else 0.0,
        },
        "by_connection_type": dict(type_stats),
        "by_connection_name": dict(name_stats),
        "timing": {
            "avg_connection_time": avg_time,
            "min_connection_time": min_time,
            "max_connection_time": max_time,
            "successful_connections": len(successful_times),
        },
    }
