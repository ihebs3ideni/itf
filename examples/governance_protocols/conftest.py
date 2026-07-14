"""Provider implementations — a mock target with typed resources.

This conftest uses the centralized contracts from ``contracts.py`` for both
the string constants and the Protocol shapes. The verify hook uses
``isinstance()`` checks against the protocols to enforce contract compliance
at composition time — before any test runs.
"""

import pytest

from score.itf.core.ctf.contracts import provides, requires
from score.itf.core.ctf.descriptor import Descriptor
from score.itf.core.ctf.target import TARGET_ANCHOR

# Import from the GOVERNANCE layer — not from any plugin implementation.
from contracts import (
    TARGET,
    EXEC,
    FILE_TRANSFER,
    NETWORK_INFO,
    ExecCapability,
    FileTransfer,
    NetworkInfo,
    TypedDut,
)

pytest_plugins = [
    "score.itf.core.itf_plugin",
    "score.itf.plugins.utility.logger.plugin",
]


@pytest.fixture
def target(dut) -> TypedDut:
    """Typed DUT wrapper — gives tests full autocomplete for free."""
    return TypedDut(dut)


# ─── Descriptors (static config) ─────────────────────────────────────────────


@pytest.hookimpl
def pytest_itf_declare(registry, config):
    registry.add_descriptor(Descriptor("target/board_name", "mock-ecu-01"))
    registry.add_descriptor(Descriptor("target/ssh_port", 22))

    # ─── Providers ────────────────────────────────────────────────────────

    @provides(TARGET_ANCHOR)
    @requires("target/board_name", "target/ssh_port")
    def mock_target(board_name, ssh_port):
        """Simulates a target board. Yields for teardown demo."""
        target = {"name": board_name, "ip": "192.168.1.100", "port": ssh_port}
        yield target
        # teardown: would disconnect / power-off in a real impl
        target["disconnected"] = True

    registry.register(mock_target)

    @provides(EXEC)
    @requires(TARGET_ANCHOR)
    def exec_capability(target):
        """Provides remote exec — must satisfy ExecCapability protocol."""

        class SshExec:
            def execute(self, cmd: str) -> tuple[int, str]:
                return (0, f"[{target['name']}] $ {cmd}")

        return SshExec()

    registry.register(exec_capability)

    @provides(FILE_TRANSFER)
    @requires(TARGET_ANCHOR)
    def file_transfer(target):
        """Provides file transfer — must satisfy FileTransfer protocol."""

        class ScpTransfer:
            def push(self, local: str, remote: str) -> None:
                pass  # scp local -> target['ip']:remote

            def pull(self, remote: str, local: str) -> None:
                pass  # scp target['ip']:remote -> local

        return ScpTransfer()

    registry.register(file_transfer)

    @provides(NETWORK_INFO)
    @requires(TARGET_ANCHOR)
    def network_info(target):
        """Provides network addressing — must satisfy NetworkInfo protocol."""

        class NetInfo:
            @property
            def ip(self) -> str:
                return target["ip"]

            @property
            def port(self) -> int:
                return target["port"]

        return NetInfo()

    registry.register(network_info)


# ─── Aliases ──────────────────────────────────────────────────────────────────


@pytest.hookimpl
def pytest_itf_aliases(dut, config):
    dut.alias("exec", EXEC)
    dut.alias("files", FILE_TRANSFER)
    dut.alias("net", NETWORK_INFO)
    dut.alias("target", TARGET)


# ─── Verify — protocol compliance check ──────────────────────────────────────


@pytest.hookimpl
def pytest_itf_verify(dut, config):
    """Assert that resolved resources match their declared protocols.

    This is the governance payoff: a provider that doesn't implement the
    protocol fails BEFORE tests run, with a clear structural error.
    """
    assert isinstance(dut.require(EXEC), ExecCapability), (
        f"Provider for {EXEC!r} does not satisfy ExecCapability protocol"
    )
    assert isinstance(dut.require(FILE_TRANSFER), FileTransfer), (
        f"Provider for {FILE_TRANSFER!r} does not satisfy FileTransfer protocol"
    )
    assert isinstance(dut.require(NETWORK_INFO), NetworkInfo), (
        f"Provider for {NETWORK_INFO!r} does not satisfy NetworkInfo protocol"
    )
