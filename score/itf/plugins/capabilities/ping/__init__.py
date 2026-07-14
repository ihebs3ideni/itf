"""Ping capability package.

Library exports: ping, ping_lost, PingComponent.
Plugin wiring lives in ``plugin.py`` (loaded via pytest_plugins).
"""

from __future__ import annotations

from score.itf.plugins.capabilities.ping.ping import ping, ping_lost, PingComponent

CAP_PING_CONTRACT = "itf/cap/ping"
IP_ADDRESS_CONTRACT = "itf/net/ip_address"


__all__ = ["ping", "ping_lost", "PingComponent", "CAP_PING_CONTRACT", "IP_ADDRESS_CONTRACT"]
