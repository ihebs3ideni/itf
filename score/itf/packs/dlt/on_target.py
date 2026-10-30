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
"""The `dlt_on_target` fixture: dlt-receive uploaded to and run on the target itself.

A pytest plugin, not a provider: each test starts its own receivers. It reaches the target only
through its contracts: one `itf.capabilities.files.transfer` and one `itf.capabilities.exec.process`
node of the root scope (named with --dlt-on-target-files / --dlt-on-target-process when several).

    def test_example(target, dlt_on_target):
        with dlt_on_target("udp", multicast_ips=["224.0.0.1"]) as receiver:
            ...
        assert "expected" in receiver.get_output()
"""

from __future__ import annotations

import logging
from contextlib import contextmanager

import pytest

from .receive.tool import Transport, bundled, protocol_arguments

logger = logging.getLogger(__name__)

REMOTE_BINARY = "/tmp/dlt-receive"
REMOTE_OUTPUT_DIR = "/tmp"
FILES = "itf.capabilities.files.transfer"
PROCESS = "itf.capabilities.exec.process"


def pytest_addoption(parser):
    group = parser.getgroup("itf-dlt")
    group.addoption(
        "--dlt-receive-on-target-path",
        default=None,
        help="dlt-receive built for the target (default: the bundled host build)",
    )
    group.addoption("--dlt-on-target-files", default=None, help="node providing files.transfer")
    group.addoption("--dlt-on-target-process", default=None, help="node providing exec.process")


def node_for(target, token: str, name: str | None):
    """The root-scope node `name`, or the only node of `token` there."""
    if name:
        return target.get(name)
    names = [n["name"] for n in target.plan()["target"]["nodes"] if n["contract"] == token]
    if len(names) != 1:
        raise pytest.UsageError(
            f"dlt_on_target needs one {token} node in the root scope, found {names or 'none'}; "
            f"name one with the matching --dlt-on-target-* option"
        )
    return target.get(names[0])


class DltReceiver:
    """An asynchronous process handle that also knows the DLT file it writes on the target."""

    def __init__(self, process, dlt_file: str):
        self._process = process
        self.dlt_file = dlt_file

    def __getattr__(self, name):
        return getattr(self._process, name)


@pytest.fixture
def dlt_on_target(request, session):
    # The ITF target from the session: a project may override the `target` fixture (a legacy layer).
    target = session.target
    files = node_for(target, FILES, request.config.getoption("dlt_on_target_files"))
    process = node_for(target, PROCESS, request.config.getoption("dlt_on_target_process"))
    files.upload(request.config.getoption("dlt_receive_on_target_path") or bundled("dlt-receive"), REMOTE_BINARY)
    process.spawn("chmod", ["+x", REMOTE_BINARY]).wait()

    started = []
    counter = 0

    @contextmanager
    def start(
        transport,
        host_ip="127.0.0.1",
        target_ip="127.0.0.1",
        multicast_ips=None,
        print_to_stdout=True,
        output_file=None,
    ):
        nonlocal counter
        counter += 1
        if not isinstance(transport, Transport):  # "tcp", or any enum member named TCP/UDP
            transport = Transport[str(getattr(transport, "name", transport)).upper()]
        dlt_file = output_file or f"{REMOTE_OUTPUT_DIR}/dlt-receive-{counter}.dlt"
        args = protocol_arguments(transport, host_ip, target_ip, multicast_ips or []) + ["-o", dlt_file]
        args += ["-a", "--stdout-flush"] if print_to_stdout else []
        handle = process.spawn(REMOTE_BINARY, args)
        started.append(handle)
        try:
            yield DltReceiver(handle, dlt_file)
        finally:
            if handle.is_running():
                handle.stop()

    yield start

    for handle in started:
        try:
            if handle.is_running():
                handle.stop()
        except Exception:
            logger.warning("Failed to stop dlt-receive on the target", exc_info=True)


__all__ = ["Transport", "dlt_on_target"]
