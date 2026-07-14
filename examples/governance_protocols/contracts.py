"""Domain contracts vocabulary — the governance layer.

This module is the SINGLE SOURCE OF TRUTH for contract strings and their
typed shapes. It has NO implementation dependencies — only stdlib typing.

Both providers (plugins, conftest) and consumers (tests) import from here.
Neither depends on the other; this module is a dependency-free leaf.

    contracts.py  (this file — leaf, no deps)
         ↑            ↑
         |            |
    conftest.py     test_*.py
    (implements)    (consumes + annotates)
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


# ─── Contract strings ─────────────────────────────────────────────────────────
# Centralized here so typos are caught at import time, not at runtime.

TARGET = "ctf/target"
EXEC = "automation/exec"
FILE_TRANSFER = "automation/file_transfer"
NETWORK_INFO = "automation/network_info"


# ─── Protocols (static typing only) ──────────────────────────────────────────
# These describe the SHAPE of the resource a provider must produce.
# They are runtime_checkable so verify hooks can assert compliance.


@runtime_checkable
class ExecCapability(Protocol):
    """Remote command execution on the target."""

    def execute(self, cmd: str) -> tuple[int, str]:
        """Run ``cmd``, return (exit_code, stdout)."""
        ...


@runtime_checkable
class FileTransfer(Protocol):
    """File push/pull between host and target."""

    def push(self, local: str, remote: str) -> None:
        """Copy a local file to the target."""
        ...

    def pull(self, remote: str, local: str) -> None:
        """Copy a file from the target to the host."""
        ...


@runtime_checkable
class NetworkInfo(Protocol):
    """Network addressing information for the target."""

    @property
    def ip(self) -> str:
        """The target's reachable IP address."""
        ...

    @property
    def port(self) -> int:
        """The primary service port."""
        ...


# ─── Typed DUT wrapper (practical middle ground) ─────────────────────────────
# Gives tests full autocomplete WITHOUT per-call annotations.
# This is a governance choice — ITF itself stays untyped and decoupled.


class TypedDut:
    """Thin typed accessor over the raw DUT — full autocomplete, zero boilerplate.

    Usage in tests::

        def test_something(dut):
            t = TypedDut(dut)
            t.exec.execute("ls")   # ← IDE resolves .execute() automatically
            t.net.ip               # ← IDE resolves .ip as str
    """

    def __init__(self, dut) -> None:
        self._dut = dut

    @property
    def exec(self) -> ExecCapability:
        """Remote command execution."""
        return self._dut.require(EXEC)

    @property
    def files(self) -> FileTransfer:
        """File push/pull."""
        return self._dut.require(FILE_TRANSFER)

    @property
    def net(self) -> NetworkInfo:
        """Network addressing."""
        return self._dut.require(NETWORK_INFO)
