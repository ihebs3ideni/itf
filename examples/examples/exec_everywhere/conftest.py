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
"""Root recipe: loads the YAML recipe named by ITF_CONFIG (one recipe per py_itf_test target)."""

import logging
import os
import socket
import time
from pathlib import Path
from typing import Protocol

from score.itf.core import delivers, hookimpl, load_init, load_setup


log = logging.getLogger("exec_everywhere")
CONSOLE = "itf.capabilities.exec.console"
EVIDENCE = Path(os.environ.get("TEST_UNDECLARED_OUTPUTS_DIR", ".")) / "evidence"


def _recipe() -> Path:
    return Path(os.environ["ITF_CONFIG"])


@hookimpl
def itf_setup(ctx):
    load_setup(ctx, _recipe())


@hookimpl
def itf_init(ctx):
    load_init(ctx, _recipe())


@hookimpl
def itf_verify(session):
    """Readiness, checked once after bring-up and before the first test: a target that cannot run a
    command, or whose console recorded nothing, fails here with a named check instead of in a test."""
    target = session.target
    log.info("verify: target offers %s", ", ".join(sorted(target.tokens())))
    if target.has(CONSOLE):
        # Before sending anything: a console that recorded no boot output at all has a problem of its own.
        first = target.console.wait_for("", timeout=10, since=0)
        session.check("console.recorded_boot", first is not None, detail=f"first recorded line: {first!r}")
    code, output = target.command.exec("echo -n ready")
    # endswith, not ==: a console may deliver its boot banner into the first command's output window
    session.check(
        "command.answers", code == 0 and output.strip().endswith("ready"), detail=f"exit {code}, output {output!r}"
    )
    if target.has("itf.capabilities.platform.instance"):
        session.check("platform.running", target.platform.running())


@hookimpl
def itf_teardown(session):
    """Evidence, collected while the target still runs and before it is dismantled: what a person
    needs to follow what the target did (console transcript, container output)."""
    target = session.target
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    if target.has(CONSOLE):
        path = EVIDENCE / "console.txt"
        path.write_text("\n".join(target.console.lines()), encoding="utf-8")
        log.info("teardown: console transcript (%d lines) saved to %s", len(target.console.lines()), path)
    container = (
        getattr(target.platform, "container", None) if target.has("itf.capabilities.platform.instance") else None
    )
    if container is not None:
        path = EVIDENCE / "container.log"
        path.write_bytes(container.logs())
        log.info("teardown: container output saved to %s", path)


class Endpoint(Protocol):
    host: str
    port: int


def _accepts_connections(endpoint: Endpoint) -> bool:
    """The device is up when it greets: a published port can accept a connection (the engine's forwarder)
    before anything inside the container listens, so a bare connect is not evidence."""
    try:
        with socket.create_connection((endpoint.host, endpoint.port), timeout=1) as connection:
            connection.settimeout(2)
            return connection.recv(1) != b""
    except OSError:
        return False


# Planned only by recipes that relate a state to it (d_serial_device.yaml): the device is up once its port
# accepts connections, which can take a moment after the container starts.
@delivers(
    "example.fake_ecu.listening",
    name="example.await_fake_ecu",
    requires=("itf.states.platform.up",),
    uses={"endpoint": "itf.capabilities.descriptor.endpoint"},
)
def await_fake_ecu(endpoint: Endpoint) -> None:
    deadline = time.monotonic() + 60
    while not _accepts_connections(endpoint):
        if time.monotonic() > deadline:
            raise TimeoutError(f"{endpoint.host}:{endpoint.port} did not accept connections within 60 s")
        time.sleep(0.5)


@await_fake_ecu.probe
def fake_ecu_listening(endpoint: Endpoint) -> bool:
    return _accepts_connections(endpoint)
