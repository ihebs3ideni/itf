# *******************************************************************************
# Copyright (c) 2026 Contributors to the Eclipse Foundation
#
# See the NOTICE file(s) distributed with this work for additional
# information regarding copyright ownership.
#
# This program and the accompanying materials are made available under the
# terms of the Apache License Version 2.0 which is available at
# https://www.apache.org/licenses/LICENSE-2.0
#
# SPDX-License-Identifier: Apache-2.0
# *******************************************************************************
"""``ctf/cap/ping`` -- a *derived* DUT capability.

Ping is not a target primitive: no target implements "ping" natively. It is
*derived* from other contracts -- run ``ping`` from the host against the
target's own IP. Its requirements are therefore:

* ``ctf/host/process``  -- host-side process runner (infrastructure), and
* ``ctf/cap/network``   -- the target's IP (target-specific knowledge).

Crucially it does NOT require ``ctf/cap/exec``: a target with no shell but a
network identity is still pingable, because the ping runs on the host. Because
the provider lives here (pure composition of contracts), no target contains any
ping code.

The provider is declared *unconditionally*: it always requires
``ctf/host/process`` and ``ctf/cap/network``. On a target that publishes no
network identity those requirements cannot be met, so the composition engine
marks ``ctf/cap/ping`` unavailable (loose mode) and dependent tests skip -- the
same outcome the old self-gating produced, now decided by the graph and run mode
instead of hand-rolled registration guards.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ctf.contracts import provides, requires

from . import network as cap_network
from .. import host as host_plugin

#: The reserved framework contract for this derived capability.
CONTRACT = "ctf/cap/ping"


@runtime_checkable
class Ping(Protocol):
    """Check whether the target answers ICMP echo from the host."""

    def ping(self) -> bool:
        """Return True if the target's IP responds to a single ping."""
        ...


class _Ping:
    def __init__(self, host: host_plugin.HostProcess, network: cap_network.Network):
        self._host = host
        self._network = network

    def ping(self) -> bool:
        ip = self._network.ip()
        code, _ = self._host.run(f"ping -c1 -W2 {ip}", timeout=10)
        return code == 0


@provides(CONTRACT)
@requires(host_plugin.CONTRACT, cap_network.CONTRACT)
def ping_capability(host: host_plugin.HostProcess, network: cap_network.Network) -> Ping:
    return _Ping(host, network)


def pytest_ctf_setup(registry, config):
    # Declared unconditionally. If the composed target publishes no network
    # identity, ``ctf/cap/ping`` is unresolvable and the engine records it as
    # unavailable (loose mode); tests requiring it then skip. No registration
    # guard is needed -- the graph and run mode decide.
    registry.register(ping_capability)
