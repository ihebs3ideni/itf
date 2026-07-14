"""Minimal example exercising the full ITF lifecycle with the logger plugin."""

import pytest
from score.itf.core.ctf.contracts import provides, requires
from score.itf.core.ctf.descriptor import Descriptor
from score.itf.core.ctf.target import TARGET_ANCHOR

pytest_plugins = [
    "score.itf.core.itf_plugin",
    "score.itf.plugins.utility.logger.plugin",
]


@pytest.hookimpl
def pytest_itf_declare(registry, config):
    registry.add_descriptor(Descriptor("itf/target/mock/image", "ubuntu:24.04"))

    @provides(TARGET_ANCHOR)
    @requires("itf/target/mock/image")
    def mock_target(image):
        return {"name": "mock-board", "image": image, "ip": "10.0.0.42"}

    registry.register(mock_target)

    @provides("itf/cap/exec")
    @requires(TARGET_ANCHOR)
    def mock_exec(target):
        class Shell:
            def execute(self, cmd):
                return (0, f"mock: {cmd}")

        return Shell()

    registry.register(mock_exec)

    @provides("itf/cap/file_transfer")
    @requires(TARGET_ANCHOR)
    def mock_ft(target):
        return {"push": lambda src, dst: None}

    registry.register(mock_ft)

    @provides("itf/net/ip_address")
    @requires(TARGET_ANCHOR)
    def mock_ip(target):
        return target["ip"]

    registry.register(mock_ip)


@pytest.hookimpl
def pytest_itf_aliases(dut, config):
    dut.alias("shell", "itf/cap/exec")
    dut.alias("files", "itf/cap/file_transfer")
    dut.alias("target", "ctf/target")


@pytest.hookimpl
def pytest_itf_verify(dut, config):
    target = dut.require("ctf/target")
    assert target["name"] == "mock-board"
