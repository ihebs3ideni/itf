"""Multi-device example: two SoCs in one ECU, per-device assemblies + bindings.

This conftest models a real automotive ECU with:
- A **safety SoC** running AUTOSAR Classic (console-only, flashable via TRACE32)
- An **integration SoC** running Linux (SSH, ping, flashable via fastboot)

Each flasher is a separate "plugin" with its own contract name
(``trace32/flash`` and ``fastboot/flash``). The conftest uses **bindings** to
wire each flasher into the generic ``cap/flash`` contract within its device
scope. Tests just call ``dut["safety"]["flash"]`` — they never know which
flasher implementation they're talking to.

Key patterns demonstrated:
1. **Plugin-specific contracts**: each flasher owns its own contract name
2. **Generic capability contract**: ``cap/flash`` is what tests consume
3. **Bindings per device**: redirect ``cap/flash``'s dependency to the right tool
4. **Same generic provider, different implementations**: ``cap/flash`` delegates
   to whichever ``flash/tool`` descriptor is bound in that scope
5. **Descriptor cascade**: devices inherit ``hw/device`` from root
"""

import logging

import pytest

from score.itf.core.ctf.contracts import provides, requires
from score.itf.core.ctf.descriptor import Descriptor
from score.itf.plugins.capabilities.ping.plugin import register_ping
from score.itf.plugins.capabilities.ssh.plugin import register_ssh

logger = logging.getLogger(__name__)

pytest_plugins = [
    "score.itf.core.itf_plugin",
    "score.itf.plugins.utility.logger.plugin",
]


# =============================================================================
# "Plugins" — each flasher is a standalone module with its own contract
# =============================================================================

# --- Lauterbach TRACE32 flasher plugin ---
# Owns contract: "trace32/flash"
# Requires: "trace32/config" (JTAG host, port)


class Trace32Flasher:
    """Lauterbach TRACE32 flash tool for safety-critical MCUs."""

    def __init__(self, jtag_host: str, jtag_port: int):
        self.jtag_host = jtag_host
        self.jtag_port = jtag_port
        self._image: str | None = None

    def flash(self, image: str) -> None:
        self._image = image
        logger.info("TRACE32: flashed %s via JTAG %s:%d", image, self.jtag_host, self.jtag_port)

    @property
    def current_image(self) -> str | None:
        return self._image


@provides("trace32/flash")
@requires("trace32/config")
def trace32_flasher(config):
    """TRACE32 plugin provider — produces a Trace32Flasher from its config."""
    return Trace32Flasher(
        jtag_host=config["jtag_host"],
        jtag_port=config["jtag_port"],
    )


# --- Android fastboot flasher plugin ---
# Owns contract: "fastboot/flash"
# Requires: "fastboot/config" (USB device path, slot)


class FastbootFlasher:
    """Android fastboot flash tool for Linux application processors."""

    def __init__(self, usb_device: str, slot: str):
        self.usb_device = usb_device
        self.slot = slot
        self._image: str | None = None

    def flash(self, image: str) -> None:
        self._image = image
        logger.info("fastboot: flashed %s to slot %s via %s", image, self.slot, self.usb_device)

    @property
    def current_image(self) -> str | None:
        return self._image


@provides("fastboot/flash")
@requires("fastboot/config")
def fastboot_flasher(config):
    """Fastboot plugin provider — produces a FastbootFlasher from its config."""
    return FastbootFlasher(
        usb_device=config["usb_device"],
        slot=config["slot"],
    )


# =============================================================================
# Generic capability — tests consume this, never the plugin-specific contracts
# =============================================================================


@provides("cap/flash")
@requires("flash/tool")  # abstract: bound to trace32/flash or fastboot/flash per device
def flash_capability(tool):
    """Generic flash capability — delegates to whichever tool is bound."""
    return tool


# =============================================================================
# Other providers (target anchors, console)
# =============================================================================


@provides("ctf/target")
@requires("hw/device")
def safety_soc(device):
    soc = {
        "name": "safety-r52",
        "device": device["name"],
        "arch": "armv7r",
        "os": "AUTOSAR Classic",
    }
    yield soc
    logger.info("Safety SoC torn down")


@provides("ctf/target")
@requires("hw/device")
def integration_soc(device):
    soc = {
        "name": "integration-a53",
        "device": device["name"],
        "arch": "aarch64",
        "os": "Linux 6.1",
    }
    yield soc
    logger.info("Integration SoC torn down")


class MockConsole:
    """Simulates a serial console to a SoC."""

    def __init__(self, soc_name: str, port: str, baudrate: int):
        self.soc_name = soc_name
        self.port = port
        self.baudrate = baudrate
        self._log: list[str] = []

    def send(self, command: str) -> str:
        response = f"[{self.soc_name}@{self.port}] $ {command}"
        self._log.append(response)
        return response

    def expect(self, pattern: str) -> bool:
        return any(pattern in line for line in self._log)


@provides("cap/console")
@requires("itf/net/endpoints")
def console_provider(eps):
    return MockConsole(
        soc_name="safety",
        port=eps.get("console", {}).get("port", "/dev/null"),
        baudrate=eps.get("console", {}).get("baudrate", 115200),
    )


# =============================================================================
# Phase: DECLARE — register everything into the right scopes
# =============================================================================


@pytest.hookimpl
def pytest_itf_declare(registry, config):
    # -- Shared root layer --
    registry.add_descriptor(
        Descriptor(
            "hw/device",
            {
                "name": "ecu-bench-01",
                "power_rail": "psu-ch3",
                "jtag": "/dev/jtag0",
            },
        )
    )

    # -- Safety SoC (TRACE32) --
    with registry.device("safety") as dev:
        dev.register(safety_soc)

        # TRACE32 plugin config + provider
        dev.add_descriptor(
            Descriptor(
                "trace32/config",
                {
                    "jtag_host": "10.0.0.10",
                    "jtag_port": 3333,
                },
            )
        )
        dev.register(trace32_flasher)

        # Generic flash capability (will be bound to trace32/flash)
        dev.add_descriptor(Descriptor("flash/tool", None))  # placeholder — bound below
        dev.register(flash_capability)

        # Other safety capabilities
        dev.add_descriptor(
            Descriptor(
                "itf/net/endpoints",
                {
                    "console": {"port": "/dev/ttyUSB0", "baudrate": 115200},
                    "jtag": {"host": "10.0.0.10", "port": 3333},
                },
            )
        )
        dev.add_descriptor(Descriptor("itf/net/ip_address", "10.0.0.10"))
        dev.register(console_provider)

    register_ping(registry, device="safety")

    # -- Integration SoC (fastboot) --
    with registry.device("integ") as dev:
        dev.register(integration_soc)

        # Fastboot plugin config + provider
        dev.add_descriptor(
            Descriptor(
                "fastboot/config",
                {
                    "usb_device": "/dev/bus/usb/001/003",
                    "slot": "a",
                },
            )
        )
        dev.register(fastboot_flasher)

        # Generic flash capability (will be bound to fastboot/flash)
        dev.add_descriptor(Descriptor("flash/tool", None))  # placeholder — bound below
        dev.register(flash_capability)

        # Other integ capabilities
        dev.add_descriptor(
            Descriptor(
                "itf/net/endpoints",
                {
                    "default": {"host": "10.0.0.2", "port": 22, "username": "root", "password": ""},
                    "debug": {"host": "10.0.0.3", "port": 22, "username": "root", "password": ""},
                },
            )
        )
        dev.add_descriptor(
            Descriptor(
                "itf/net/ssh_endpoint",
                {
                    "host": "10.0.0.2",
                    "port": 22,
                    "username": "root",
                    "password": "",
                },
            )
        )
        dev.add_descriptor(Descriptor("itf/net/ip_address", "10.0.0.2"))

    register_ssh(registry, device="integ")
    register_ping(registry, device="integ")

    # -- Bindings: wire generic cap/flash to the right tool per device --
    # Safety: cap/flash requires "flash/tool" → redirect to "trace32/flash"
    registry.device_registry("safety").bind("cap/flash", "flash/tool", "trace32/flash")
    # Integ: cap/flash requires "flash/tool" → redirect to "fastboot/flash"
    registry.device_registry("integ").bind("cap/flash", "flash/tool", "fastboot/flash")

    # Apply bindings on device registries
    registry.device_registry("safety").apply_bindings()
    registry.device_registry("integ").apply_bindings()


# =============================================================================
# Phase: ALIASES — project vocabulary
# =============================================================================


@pytest.hookimpl
def pytest_itf_aliases(dut, config):
    # Root-level (shared facts)
    dut.alias("device", "hw/device")

    # Device-local aliases — same names, different scopes
    for name in dut.devices():
        proxy = dut[name]
        proxy.alias("target", "ctf/target")
        proxy.alias("flash", "cap/flash")  # tests say dut["safety"]["flash"]
        proxy.alias("ping", "itf/cap/ping")
        proxy.alias("endpoints", "itf/net/endpoints")

    # Device-specific extras
    if "safety" in dut.devices():
        dut["safety"].alias("console", "cap/console")
        dut["safety"].alias("trace32", "trace32/flash")  # direct access if needed
    if "integ" in dut.devices():
        dut["integ"].alias("ssh", "itf/cap/ssh")
        dut["integ"].alias("fastboot", "fastboot/flash")  # direct access if needed
