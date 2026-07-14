"""Sample tests that use the DUT — these will show up in test.log."""

import logging

logger = logging.getLogger(__name__)


def test_exec_capability(dut):
    logger.info("Requesting exec capability")
    shell = dut.require("itf/cap/exec")
    code, out = shell.execute("systemctl is-active myapp")
    logger.debug("exec returned: code=%d, out=%s", code, out)
    assert code == 0


def test_alias_access(dut):
    logger.info("Using alias 'shell'")
    shell = dut["shell"]
    assert shell is not None
    code, out = shell.execute("cat /etc/os-release")
    logger.debug("Result: %s", out)


def test_ip_address(dut):
    ip = dut.require("itf/net/ip_address")
    logger.info("Target IP: %s", ip)
    assert ip == "10.0.0.42"


def test_target_info(dut):
    target = dut["target"]
    logger.info("Target: %s", target)
    assert target["image"] == "ubuntu:24.04"
