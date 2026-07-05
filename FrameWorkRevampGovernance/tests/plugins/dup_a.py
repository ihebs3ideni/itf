"""One of two plugins that both provide the same contract (a duplicate)."""

from __future__ import annotations

from ctf.contracts import provides


@provides("score/doip/client")
def doip_client_a():
    return "a"


def pytest_ctf_setup(registry, config):
    registry.register(doip_client_a)
