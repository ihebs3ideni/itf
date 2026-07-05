"""A plugin whose contract names ignore the namespace convention."""

from __future__ import annotations

from ctf.contracts import provides


@provides("client")
def client():
    return object()


def pytest_ctf_setup(registry, config):
    registry.register(client)
