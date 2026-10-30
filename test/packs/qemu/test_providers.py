# *******************************************************************************
# Copyright (c) 2026 Contributors to the Eclipse Foundation
#
# See the NOTICE file(s) distributed with this work for additional
# information regarding copyright ownership.
#
# This program and the accompanying materials are made available under the
# terms of the Apache License Version 2.0 which is available at
# https://www.apache.org/licenses/LICENSE-2.0
#
# SPDX-License-Identifier: Apache-2.0
# *******************************************************************************
"""QEMU providers without QEMU: configuration-derived endpoint and login, the console, preconditions."""

import json
import threading
import time

import pytest

from score.itf.packs.qemu.console import QemuConsole
from score.itf.packs.qemu.descriptors import QemuCredentials, QemuEndpoint
from score.itf.packs.qemu.platform import QemuPlatform

BASE = {
    "networks": [{"name": "tap0", "ip_address": "169.254.158.190", "gateway": "169.254.21.88"}],
    "ssh_port": 2222,
    "qemu_num_cores": 2,
    "qemu_ram_size": "1G",
}


def _platform(tmp_path, **extra):
    config = tmp_path / "qemu.json"
    config.write_text(json.dumps({**BASE, **extra}), encoding="utf-8")
    return QemuPlatform({"config_file": str(config), "kernel": "ifs.img"})


def test_endpoint_is_the_first_network_and_ssh_port(tmp_path):
    endpoint = QemuEndpoint(_platform(tmp_path))
    assert (endpoint.host, endpoint.port) == ("169.254.158.190", 2222)


@pytest.mark.parametrize(
    "ssh_auth, expected",
    [
        (None, ("root", "", None)),
        ({"username": "qnxuser", "password": "qnxuser"}, ("qnxuser", "qnxuser", None)),
        ({"username": "root", "pkey_path": "/keys/id"}, ("root", None, "/keys/id")),
    ],
)
def test_credentials_follow_ssh_auth(tmp_path, ssh_auth, expected):
    extra = {"ssh_auth": ssh_auth} if ssh_auth else {}
    credentials = QemuCredentials(_platform(tmp_path, **extra))
    assert (credentials.user, credentials.password, credentials.key_path) == expected


def test_credentials_reject_an_empty_username(tmp_path):
    with pytest.raises(ValueError, match="username"):
        QemuCredentials(_platform(tmp_path, ssh_auth={"username": ""}))


def test_platform_needs_a_kernel_or_a_rootfs(tmp_path):
    config = tmp_path / "qemu.json"
    config.write_text(json.dumps(BASE), encoding="utf-8")
    with pytest.raises(ValueError, match="kernel, a rootfs"):
        QemuPlatform({"config_file": str(config)})


def test_start_without_qemu_installed_names_the_missing_binary(tmp_path):
    platform = _platform(tmp_path)
    platform.binary_dir = str(tmp_path / "nowhere")
    with pytest.raises(RuntimeError, match="qemu-system-x86_64 is missing"):
        platform.start()


class _FakePipeConsole:
    """Echoes what is written, then prints the exit-status marker, like a shell on a UART."""

    def __init__(self):
        self._lines: list[str] = []
        self._cv = threading.Condition()

    def emit(self, line: str) -> None:
        with self._cv:
            self._lines.append(line)
            self._cv.notify()

    def readline(self, block=False, timeout=None):
        with self._cv:
            if not self._lines:
                self._cv.wait(timeout)
            if not self._lines:
                raise TimeoutError
            return self._lines.pop(0)

    def write(self, text: str) -> None:
        command, _, marker = text.partition("; echo ")
        self.emit(text)
        self.emit("hello" if "echo hello" in command else "")
        self.emit(marker.replace("$?", "3" if "false" in command else "0"))


class _Platform:
    def __init__(self):
        self.console = _FakePipeConsole()


def test_console_records_lines_and_runs_commands():
    platform = _Platform()
    console = QemuConsole(platform)
    console.open()
    try:
        platform.console.emit("U-Boot 2026.01")
        assert console.wait_for("U-Boot", timeout=5, since=0) == "U-Boot 2026.01"
        mark = console.mark()
        code, output = console.run("echo hello", timeout=5)
        assert code == 0 and "hello" in output
        assert console.run("false", timeout=5)[0] == 3
        assert all("U-Boot" not in line for line in console.lines(mark))
    finally:
        console.close()
    assert not console.is_open()


def test_console_wait_for_times_out_with_none():
    console = QemuConsole(_Platform())
    console.open()
    try:
        started = time.monotonic()
        assert console.wait_for("never", timeout=0.3) is None
        assert time.monotonic() - started >= 0.3
    finally:
        console.close()
