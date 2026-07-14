"""Tests that consume governed contracts with full IDE autocomplete.

Note how each test annotates the resolved resource with the Protocol type.
The IDE provides autocomplete for .execute(), .push(), .ip, etc. — all
without importing anything from the provider implementation.
"""

import logging

from contracts import (
    EXEC,
    FILE_TRANSFER,
    NETWORK_INFO,
    ExecCapability,
    FileTransfer,
    NetworkInfo,
)

logger = logging.getLogger(__name__)


def test_exec_via_protocol(dut):
    """IDE knows shell.execute() returns tuple[int, str]."""
    shell: ExecCapability = dut.require(EXEC)

    code, output = shell.execute("uname -a")
    logger.info("exec result: code=%d output=%r", code, output)
    assert code == 0
    assert "mock-ecu-01" in output


def test_exec_via_alias(dut):
    """Aliases work the same — annotate for autocomplete."""
    shell: ExecCapability = dut["exec"]

    code, _ = shell.execute("systemctl status myapp")
    assert code == 0


def test_file_transfer(dut):
    """IDE knows files.push() and files.pull() signatures."""
    files: FileTransfer = dut.require(FILE_TRANSFER)

    # Full autocomplete: push(local, remote), pull(remote, local)
    files.push("/tmp/firmware.bin", "/opt/update/firmware.bin")
    files.pull("/var/log/syslog", "/tmp/target_syslog.txt")


def test_network_info_properties(dut):
    """IDE resolves .ip as str and .port as int."""
    net: NetworkInfo = dut.require(NETWORK_INFO)

    logger.info("Target at %s:%d", net.ip, net.port)
    assert net.ip == "192.168.1.100"
    assert net.port == 22


def test_alias_network(dut):
    """Same protocol, accessed via alias."""
    net: NetworkInfo = dut["net"]
    assert isinstance(net.ip, str)


# ─── TypedDut approach: zero annotations needed per call ──────────────────────
# The `target` fixture (from conftest) wraps dut in TypedDut automatically.
# Testers just request `target` and get full autocomplete — no manual wrapping.


def test_typed_dut_exec(target):
    """target.exec gives autocomplete without any annotations."""
    # IDE resolves: target.exec.execute(cmd: str) -> tuple[int, str]
    code, output = target.exec.execute("whoami")
    assert code == 0
    assert "mock-ecu-01" in output


def test_typed_dut_files(target):
    """target.files exposes .push() and .pull() with full signatures."""
    # IDE resolves: target.files.push(local: str, remote: str) -> None
    target.files.push("/tmp/app.bin", "/opt/app.bin")
    target.files.pull("/var/log/app.log", "/tmp/app.log")


def test_typed_dut_network(target):
    """target.net exposes .ip as str and .port as int."""
    # IDE resolves: target.net.ip -> str, target.net.port -> int
    logger.info("Typed access: %s:%d", target.net.ip, target.net.port)
    assert target.net.ip == "192.168.1.100"
    assert target.net.port == 22
