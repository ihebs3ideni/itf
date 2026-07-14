"""Tests for the contract middleware example.

Demonstrates:
1. Middleware — endpoint map → flat IP list transformation
2. Binding — heartbeat plugin redirected to a dedicated subnet
3. Aliasing — short names for long contract strings
"""

import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Middleware: endpoint map transformed into flat IP list
# ═══════════════════════════════════════════════════════════════════════════════


class TestMiddleware:
    """The conftest middleware provider bridges endpoint map → IP list."""

    def test_ip_list_extracted_from_endpoints(self, dut):
        """The middleware extracted unique hosts from the endpoint map."""
        ip_list = dut.require("acme/monitor/ip_list")
        assert isinstance(ip_list, list)
        assert "10.0.0.2" in ip_list
        assert "10.0.0.3" in ip_list
        assert "10.0.0.4" in ip_list

    def test_ip_list_is_sorted_and_deduped(self, dut):
        """Middleware sorts and deduplicates the IPs."""
        ip_list = dut.require("acme/monitor/ip_list")
        assert ip_list == sorted(set(ip_list))

    def test_monitor_received_transformed_data(self, dut):
        """AcmeMonitor got its list[str], not a dict."""
        monitor = dut["monitor"]
        assert isinstance(monitor.ip_list, list)
        assert all(isinstance(ip, str) for ip in monitor.ip_list)

    def test_monitor_has_all_hosts(self, dut):
        """Monitor sees every host from the endpoint map."""
        monitor = dut["monitor"]
        assert set(monitor.ip_list) == {"10.0.0.2", "10.0.0.3", "10.0.0.4"}

    def test_endpoint_map_unchanged(self, dut):
        """The original endpoint map is still available unmodified."""
        endpoints = dut["endpoints"]
        assert "eth0" in endpoints
        assert endpoints["eth0"]["host"] == "10.0.0.2"
        assert endpoints["debug"]["host"] == "10.0.0.3"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Binding: heartbeat uses a different endpoint map
# ═══════════════════════════════════════════════════════════════════════════════


class TestBinding:
    """The binding hook redirected the heartbeat to a dedicated subnet."""

    def test_heartbeat_on_dedicated_subnet(self, dut):
        """Heartbeat was bound to the heartbeat endpoint map, not the main one."""
        heartbeat = dut["heartbeat"]
        # The heartbeat endpoint map has 192.168.100.2, not 10.0.0.x
        assert heartbeat.host == "192.168.100.2"
        assert heartbeat.port == 5555

    def test_heartbeat_not_on_main_network(self, dut):
        """Binding prevented the heartbeat from using the main endpoint map."""
        heartbeat = dut["heartbeat"]
        main_hosts = {"10.0.0.2", "10.0.0.3", "10.0.0.4"}
        assert heartbeat.host not in main_hosts

    def test_heartbeat_is_running(self, dut):
        """Heartbeat started automatically (yield-based provider)."""
        heartbeat = dut["heartbeat"]
        assert heartbeat.is_running


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Aliasing: short names work transparently
# ═══════════════════════════════════════════════════════════════════════════════


class TestAliasing:
    """Aliases give tests a clean vocabulary."""

    def test_alias_target(self, dut):
        target = dut["target"]
        assert target["name"] == "bench-dut-07"

    def test_alias_monitor(self, dut):
        monitor = dut["monitor"]
        assert hasattr(monitor, "ip_list")

    def test_alias_heartbeat(self, dut):
        heartbeat = dut["heartbeat"]
        assert hasattr(heartbeat, "host")

    def test_alias_equals_raw_contract(self, dut):
        """Alias resolves to the same object as the raw contract."""
        assert dut["monitor"] is dut.require("acme/monitor")
        assert dut["heartbeat"] is dut.require("itf/cap/heartbeat")
        assert dut["endpoints"] is dut.require("itf/net/endpoints")

    def test_alias_ip_list(self, dut):
        """Even the middleware output has an alias."""
        ip_list = dut["ip_list"]
        assert isinstance(ip_list, list)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Integration: all three together
# ═══════════════════════════════════════════════════════════════════════════════


class TestIntegration:
    """End-to-end: middleware + binding + aliasing in one graph."""

    def test_graph_has_all_contracts(self, dut):
        """The full graph includes target, endpoints, middleware output, and capabilities."""
        assert dut.available("ctf/target")
        assert dut.available("itf/net/endpoints")
        assert dut.available("itf/net/endpoints/heartbeat")
        assert dut.available("acme/monitor/ip_list")
        assert dut.available("acme/monitor")
        assert dut.available("itf/cap/heartbeat")

    def test_middleware_and_binding_are_independent(self, dut):
        """Middleware reads the main endpoints; heartbeat reads the bound one.
        They don't interfere with each other."""
        monitor = dut["monitor"]
        heartbeat = dut["heartbeat"]

        # Monitor got IPs from the main map
        assert "10.0.0.2" in monitor.ip_list
        # Heartbeat got its host from the heartbeat-specific map
        assert heartbeat.host == "192.168.100.2"

    def test_no_contract_leaks(self, dut):
        """Heartbeat-specific endpoints don't bleed into the monitor's IP list."""
        ip_list = dut["ip_list"]
        assert "192.168.100.2" not in ip_list
