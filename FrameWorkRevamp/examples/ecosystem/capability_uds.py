"""CAPABILITY plugin: UDS client.

Depends on ``doip/client`` -- another *capability*, not a target. It has no idea
where the DoIP client comes from; it only knows the contract string. This is how
capabilities compose on top of each other without coupling.
"""

from __future__ import annotations

from ctf.contracts import provides, requires


class UdsClient:
    def __init__(self, doip) -> None:
        self.doip = doip

    def read_did(self, did: int) -> bytes:
        return self.doip.send(f"read:{did:#06x}".encode())


@provides("uds/client")
@requires("doip/client")
def uds_client(doip) -> UdsClient:
    return UdsClient(doip)


def pytest_ctf_setup(registry, config):
    registry.register(uds_client)
