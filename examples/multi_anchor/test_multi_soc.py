"""Tests demonstrating scoped multi-device capabilities.

Uses the device-proxy DUT interface::

    dut["integ"]["ssh"]       # integration device's SSH
    dut["safety"]["console"]  # safety device's console
    dut["device"]             # root alias — shared device layer
"""

import logging

import pytest

from score.itf.core.capability_gating import requires_capabilities

logger = logging.getLogger(__name__)


# ─── Shared device layer ─────────────────────────────────────────────────────


class TestSharedDevice:
    """The device layer is shared — a root-level descriptor."""

    def test_device_is_shared(self, dut):
        device = dut["device"]
        assert device["name"] == "ecu-bench-01"
        assert device["power_rail"] == "psu-ch3"

    def test_both_socs_see_same_device(self, dut):
        safety = dut["safety"]["target"]
        integ = dut["integ"]["target"]
        assert safety["device"] == integ["device"] == "ecu-bench-01"


# ─── Safety SoC capabilities ─────────────────────────────────────────────────


class TestSafetySoC:
    """Safety SoC: AUTOSAR Classic, console + flash, NO SSH."""

    def test_safety_soc_info(self, dut):
        safety = dut["safety"]["target"]
        assert safety["os"] == "AUTOSAR Classic"
        assert safety["arch"] == "armv7r"

    def test_safety_console(self, dut):
        console = dut["safety"]["console"]
        response = console.send("diag read_dtc")
        assert "safety" in response.lower() or "ttyUSB0" in response
        logger.info("Safety console: %s", response)

    def test_safety_flash(self, dut):
        flasher = dut["safety"]["flash"]
        assert flasher.jtag_host == "10.0.0.10"
        assert flasher.jtag_port == 3333
        flasher.flash("autosar_safety_v2.1.bin")
        assert flasher.current_image == "autosar_safety_v2.1.bin"
        logger.info("Safety flashed with %s", flasher.current_image)

    def test_safety_ping(self, dut):
        """Ping resolves against the safety SoC's scoped IP address."""
        pinger = dut["safety"]["ping"]
        assert pinger is not None
        assert pinger._address == "10.0.0.10"

    def test_safety_has_no_ssh(self, dut):
        """AUTOSAR Classic doesn't run an SSH server."""
        assert not dut["safety"].available("ssh")


# ─── Integration SoC capabilities ────────────────────────────────────────────


class TestIntegrationSoC:
    """Integration SoC: Linux, SSH + ping + flash, NO console."""

    def test_integration_soc_info(self, dut):
        integ = dut["integ"]["target"]
        assert integ["os"] == "Linux 6.1"
        assert integ["arch"] == "aarch64"

    def test_integration_ssh(self, dut):
        """SSH factory resolves against the integration SoC's SSH endpoint."""
        ssh_factory = dut["integ"]["ssh"]
        assert ssh_factory is not None
        assert ssh_factory._endpoint.host == "10.0.0.2"
        assert ssh_factory._endpoint.port == 22

    def test_integration_flash(self, dut):
        flasher = dut["integ"]["flash"]
        assert flasher.usb_device == "/dev/bus/usb/001/003"
        assert flasher.slot == "a"
        flasher.flash("linux_integ_v5.3.img")
        assert flasher.current_image == "linux_integ_v5.3.img"
        logger.info("Integration flashed with %s", flasher.current_image)

    def test_integration_ping(self, dut):
        """Ping resolves against the integration SoC's primary IP address."""
        pinger = dut["integ"]["ping"]
        assert pinger is not None
        assert pinger._address == "10.0.0.2"

    def test_integration_has_no_console(self, dut):
        """Linux SoC doesn't have a serial console registered."""
        assert not dut["integ"].available("console")


# ─── Cross-device: different flashers, same contract ─────────────────────────


class TestCrossDevice:
    """Both devices are flashable, but with different tools."""

    def test_different_flash_tools(self, dut):
        safety_flash = dut["safety"]["flash"]
        integ_flash = dut["integ"]["flash"]
        # Different types — TRACE32 vs fastboot
        assert hasattr(safety_flash, "jtag_host")
        assert hasattr(integ_flash, "usb_device")
        assert not hasattr(safety_flash, "usb_device")
        assert not hasattr(integ_flash, "jtag_host")

    def test_flash_both_devices(self, dut):
        """Flash both devices independently."""
        dut["safety"]["flash"].flash("safety_v3.0.bin")
        dut["integ"]["flash"].flash("linux_v6.0.img")

        assert dut["safety"]["flash"].current_image == "safety_v3.0.bin"
        assert dut["integ"]["flash"].current_image == "linux_v6.0.img"

    def test_both_devices_are_detected(self, dut):
        """Both devices have registered contributions."""
        devices = dut.devices()
        assert "safety" in devices
        assert "integ" in devices

    def test_same_contract_different_devices(self, dut):
        """net/endpoints exists in both devices with different values."""
        safety_eps = dut["safety"]["endpoints"]
        integ_eps = dut["integ"]["endpoints"]
        assert "console" in safety_eps  # safety has console endpoint
        assert "default" in integ_eps  # integ has default SSH endpoint
        assert set(safety_eps.keys()) != set(integ_eps.keys())


# ─── Independent lifecycle ────────────────────────────────────────────────────


class TestIndependentLifecycle:
    """Each device can be rebuilt independently."""

    def test_rebuild_integration_keeps_safety(self, dut):
        safety_before = dut["safety"]["target"]
        integ_before = dut["integ"]["target"]

        torn = dut["integ"].rebuild("ctf/target")
        logger.info("Torn down during integration rebuild: %s", torn)

        safety_after = dut["safety"]["target"]
        assert safety_after is safety_before

        integ_after = dut["integ"]["target"]
        assert integ_after is not integ_before
        assert integ_after["name"] == "integration-a53"

    def test_rebuild_safety_keeps_integration(self, dut):
        integ_before = dut["integ"]["target"]
        safety_before = dut["safety"]["target"]

        torn = dut["safety"].rebuild("ctf/target")
        logger.info("Torn down during safety rebuild: %s", torn)

        integ_after = dut["integ"]["target"]
        assert integ_after is integ_before

        safety_after = dut["safety"]["target"]
        assert safety_after is not safety_before

    def test_capability_gating(self, dut):
        """Missing per-device capabilities are reflected in availability."""
        assert not dut["safety"].available("ssh")
        assert dut["integ"].available("ssh")


# ─── Endpoint map access ─────────────────────────────────────────────────────


class TestEndpointMaps:
    """Each device's endpoint map is accessible through its proxy."""

    def test_safety_endpoints(self, dut):
        endpoints = dut["safety"]["endpoints"]
        assert "console" in endpoints
        assert "jtag" in endpoints
        assert endpoints["console"]["port"] == "/dev/ttyUSB0"

    def test_integration_endpoints(self, dut):
        endpoints = dut["integ"]["endpoints"]
        assert "default" in endpoints
        assert "debug" in endpoints
        assert endpoints["default"]["host"] == "10.0.0.2"
        assert endpoints["debug"]["host"] == "10.0.0.3"


# ─── Capability gating with device scope ──────────────────────────────────────


class TestRequiresCapabilitiesWithDevice:
    """@requires_capabilities supports device= for scoped checks."""

    @requires_capabilities("itf/cap/ssh", device="integ")
    def test_ssh_on_integ_runs(self, dut):
        """SSH is available on integ — test runs normally."""
        ssh = dut["integ"]["ssh"]
        assert ssh is not None

    @requires_capabilities("itf/cap/ssh", device="safety")
    def test_ssh_on_safety_skips(self, dut):
        """SSH is NOT available on safety — test should be skipped."""
        pytest.fail("Should have been skipped")

    @requires_capabilities("cap/flash", device="safety")
    def test_flash_on_safety_runs(self, dut):
        """Flash is available on safety (via TRACE32 binding)."""
        flasher = dut["safety"]["flash"]
        flasher.flash("test.bin")
        assert flasher.current_image == "test.bin"

    @requires_capabilities("cap/flash", device="integ")
    def test_flash_on_integ_runs(self, dut):
        """Flash is available on integ (via fastboot binding)."""
        flasher = dut["integ"]["flash"]
        flasher.flash("test.img")
        assert flasher.current_image == "test.img"

    @requires_capabilities("cap/console", device="integ")
    def test_console_on_integ_skips(self, dut):
        """Console is NOT available on integ — test should be skipped."""
        pytest.fail("Should have been skipped")

    @requires_capabilities("itf/cap/ping", device="safety")
    @requires_capabilities("itf/cap/ping", device="integ")
    def test_ping_on_both_devices(self, dut):
        """Ping is available on both devices — stacked decorators."""
        assert dut["safety"]["ping"] is not None
        assert dut["integ"]["ping"] is not None
