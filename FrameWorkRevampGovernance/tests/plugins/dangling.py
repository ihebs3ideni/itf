"""A plugin that requires a contract nobody provides."""

from __future__ import annotations

from ctf.contracts import provides, requires


@provides("score/uds/client")
@requires("score/missing/thing")
def uds_client(thing):
    return thing


def pytest_ctf_setup(registry, config):
    registry.register(uds_client)
