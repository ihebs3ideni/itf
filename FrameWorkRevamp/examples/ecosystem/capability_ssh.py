"""CAPABILITY plugin: SSH client.

Consumes ``endpoint/ssh`` and produces ``ssh/client``. Uses a generator provider
so the connection is torn down (``closed = True``) after each test.
"""

from __future__ import annotations

from ctf.contracts import provides, requires


class SshClient:
    def __init__(self, host: str) -> None:
        self.host = host
        self.closed = False

    def run(self, command: str) -> str:
        return f"[{self.host}] {command}: ok"


@provides("ssh/client")
@requires("endpoint/ssh")
def ssh_client(host: str):
    client = SshClient(host)
    yield client
    client.closed = True  # teardown


def pytest_ctf_setup(registry, config):
    registry.register(ssh_client)
