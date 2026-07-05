"""CAPABILITY plugin: DoIP client.

Consumes the ``transport/doip`` fact (from *any* target that publishes it) and
produces a ``doip/client`` resource. It never references a target class.
"""

from __future__ import annotations

from ctf.contracts import provides, requires


class DoipClient:
    def __init__(self, endpoint: str) -> None:
        self.endpoint = endpoint

    def send(self, payload: bytes) -> bytes:
        return b"ack:" + payload


@provides("doip/client")
@requires("transport/doip")
def doip_client(endpoint: str) -> DoipClient:
    return DoipClient(endpoint)


def pytest_ctf_setup(registry, config):
    registry.register(doip_client)
