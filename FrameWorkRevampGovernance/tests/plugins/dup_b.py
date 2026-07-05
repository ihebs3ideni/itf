"""The second plugin that also provides ``score/doip/client`` (a duplicate)."""

from __future__ import annotations

from ctf.contracts import provides


@provides("score/doip/client")
def doip_client_b():
    return "b"


def pytest_ctf_setup(registry, config):
    registry.register(doip_client_b)
