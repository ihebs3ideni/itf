"""Contract middleware example: adapting between incompatible schemas.

Real-world scenario
-------------------
- The **target plugin** publishes ``itf/net/endpoints`` as a *named map*::

      {"eth0": {"host": "10.0.0.2", "port": 22}, "debug": {"host": "10.0.0.3"}}

- A **third-party monitoring plugin** (``acme_monitor``) requires a flat list
  of IP addresses under ``acme/monitor/ip_list`` — it predates the endpoint
  map convention and cannot be changed.

- A **heartbeat plugin** requires ``itf/net/endpoints`` but we want it to use
  a *different* endpoint map scoped to a dedicated heartbeat network.

This conftest demonstrates three integration techniques:

1. **Contract middleware** — a provider in conftest that consumes one contract
   and publishes another, transforming the data in between.
2. **Binding** — redirecting a provider's dependency so it reads from a
   different contract than the one it declared.
3. **Aliasing** — giving contracts short, project-level names for test code.
"""

import logging

import pytest

from score.itf.core.ctf.contracts import Provider, provides, requires
from score.itf.core.ctf.descriptor import Descriptor
from score.itf.core.ctf import TARGET_ANCHOR

logger = logging.getLogger(__name__)

pytest_plugins = [
    "score.itf.core.itf_plugin",
    "score.itf.plugins.utility.logger.plugin",
]


# ═══════════════════════════════════════════════════════════════════════════════
# Simulated third-party plugin (cannot be modified)
# ═══════════════════════════════════════════════════════════════════════════════
# In reality this would live in a separate package. It requires a flat list of
# IP strings — it has no idea what an "endpoint map" is.


class AcmeMonitor:
    """Third-party monitor that only understands ``list[str]``."""

    def __init__(self, ip_list: list[str]):
        self.ip_list = ip_list
        self._active = False

    def start(self):
        self._active = True
        logger.info("AcmeMonitor started, watching: %s", self.ip_list)

    def stop(self):
        self._active = False

    @property
    def is_active(self) -> bool:
        return self._active


def _register_acme_monitor(registry):
    """Pretend this is how the third-party plugin registers itself."""
    registry.add_provider(
        Provider(
            provides="acme/monitor",
            requires=("acme/monitor/ip_list",),  # ← their contract, not ours
            factory=lambda ip_list: AcmeMonitor(ip_list),
            name="acme_monitor_plugin",
        )
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Simulated heartbeat plugin (generic, uses itf/net/endpoints)
# ═══════════════════════════════════════════════════════════════════════════════


class HeartbeatSender:
    """Sends periodic UDP heartbeats to a host."""

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self._running = False

    def start(self):
        self._running = True
        logger.info("Heartbeat → %s:%d", self.host, self.port)

    def stop(self):
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running


def _register_heartbeat(registry):
    """Registers a heartbeat provider that reads the default endpoint."""

    @provides("itf/cap/heartbeat")
    @requires("itf/net/endpoints")  # ← generic, but we'll rebind it
    def heartbeat_provider(endpoints):
        # Resolve "default" from whichever endpoint map we get
        entry = endpoints.get("default", next(iter(endpoints.values())))
        sender = HeartbeatSender(host=entry["host"], port=entry.get("port", 5555))
        sender.start()
        yield sender
        sender.stop()

    registry.register(heartbeat_provider)


# ═══════════════════════════════════════════════════════════════════════════════
# Phase: DECLARE
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.hookimpl
def pytest_itf_declare(registry, config):
    # ── Target ────────────────────────────────────────────────────────────
    @provides(TARGET_ANCHOR)
    def target():
        return {"name": "bench-dut-07", "platform": "linux"}

    registry.register(target)

    # ── Primary endpoint map (what the target plugin would publish) ───────
    registry.add_descriptor(
        Descriptor(
            "itf/net/endpoints",
            {
                "eth0": {"host": "10.0.0.2", "port": 22, "username": "root"},
                "debug": {"host": "10.0.0.3", "port": 22, "username": "debug"},
                "mgmt": {"host": "10.0.0.4"},
            },
        )
    )

    # ── Dedicated heartbeat network (different subnet, different map) ─────
    registry.add_descriptor(
        Descriptor(
            "itf/net/endpoints/heartbeat",
            {
                "default": {"host": "192.168.100.2", "port": 5555},
            },
        )
    )

    # ── Register third-party and internal plugins ────────────────────────
    _register_acme_monitor(registry)
    _register_heartbeat(registry)

    # ══════════════════════════════════════════════════════════════════════
    # MIDDLEWARE PROVIDER
    # ══════════════════════════════════════════════════════════════════════
    # The AcmeMonitor plugin wants ``acme/monitor/ip_list`` (a list[str]).
    # We have ``itf/net/endpoints`` (a dict of dicts).
    # This provider bridges the gap: it consumes the endpoint map and
    # produces the flat IP list the plugin needs.
    #
    # This is a *conftest-level* provider — it's project glue, not a
    # reusable plugin. It sits in the graph like any other provider.

    @provides("acme/monitor/ip_list")
    @requires("itf/net/endpoints")
    def endpoints_to_ip_list(endpoints):
        """Middleware: extract unique hosts from the endpoint map."""
        seen = set()
        ip_list = []
        for entry in endpoints.values():
            host = entry.get("host")
            if host and host not in seen:
                seen.add(host)
                ip_list.append(host)
        return sorted(ip_list)

    registry.register(endpoints_to_ip_list)


# ═══════════════════════════════════════════════════════════════════════════════
# Phase: BINDINGS
# ═══════════════════════════════════════════════════════════════════════════════
# The heartbeat plugin declared ``@requires("itf/net/endpoints")`` — the
# generic endpoint map. But we want it to use the *heartbeat-specific* map
# on a dedicated subnet. Binding redirects the requirement without touching
# the plugin code.


@pytest.hookimpl
def pytest_itf_bindings(registry, config):
    registry.bind(
        "itf/cap/heartbeat",  # provider contract
        "itf/net/endpoints",  # what it asked for
        "itf/net/endpoints/heartbeat",  # what it should actually get
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Phase: ALIASES
# ═══════════════════════════════════════════════════════════════════════════════
# Give contracts short names so tests read like domain language.


@pytest.hookimpl
def pytest_itf_aliases(dut, config):
    dut.alias("target", TARGET_ANCHOR)
    dut.alias("monitor", "acme/monitor")
    dut.alias("heartbeat", "itf/cap/heartbeat")
    dut.alias("endpoints", "itf/net/endpoints")
    dut.alias("ip_list", "acme/monitor/ip_list")


# ═══════════════════════════════════════════════════════════════════════════════
# Phase: VERIFY
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.hookimpl
def pytest_itf_verify(dut, config):
    target = dut.require(TARGET_ANCHOR)
    logger.info("Verify: target is %s", target["name"])

    monitor = dut.require("acme/monitor")
    assert isinstance(monitor.ip_list, list)
    logger.info("Verify: monitor watching %s", monitor.ip_list)

    heartbeat = dut.require("itf/cap/heartbeat")
    assert heartbeat.is_running
    logger.info("Verify: heartbeat active → %s:%d", heartbeat.host, heartbeat.port)
