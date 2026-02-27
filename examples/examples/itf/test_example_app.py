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
"""Component tests for the C++ example-app using the ``target`` fixture.

The ``target`` fixture yields a :class:`DockerTarget` that has been
started from the ``--docker-image`` / ``--docker-image-bootstrap`` CLI options.
Tests exercise the binary directly inside the container and demonstrate
packet capture with :class:`TcpDumpCapture`.
"""

import os
import time

import score.itf.plugins.core
from score.itf.core.com.tcpdump import TcpDumpCapture


def test_example_app_runs_successfully(target):
    """The example-app binary exits with code 0."""
    exit_code, output = target.exec(["/example-app"], detach=False)
    assert exit_code == 0


def test_example_app_stdout_contains_hello(target):
    """The example-app prints 'Hello!' to stdout."""
    exit_code, output = target.exec(["/example-app"], detach=False)
    assert exit_code == 0
    assert b"Hello!" in output


def test_example_app_returns_zero(target):
    """Explicitly verify the return code via shell wrapper."""
    exit_code, output = target.exec(
        ["/bin/sh", "-c", "/example-app; echo \"RC=$?\""],
        detach=False,
    )
    assert exit_code == 0
    assert b"RC=0" in output


@score.itf.plugins.core.requires_capabilities("tcpdump")
def test_example_app_udp_traffic_captured(target):
    """Run example-app with --udp-port and --payload, verify the payload appears in the pcap.

    UDP is connectionless — the datagram is sent even without a listener,
    so tcpdump will always see it on the wire.

    Demonstrates several :class:`TcpDumpCapture` parameters:

    - ``interface`` — capture only on loopback.
    - ``target_pcap_path`` — write pcap to a custom path on the target.
    - ``snapshot_length`` — limit per-packet capture to 256 bytes.
    - ``extra_args`` — disable checksum verification.
    """
    payload = "ITF_TCPDUMP_TEST_PAYLOAD_42"

    with TcpDumpCapture(
        target.tcpdump_handler(),
        interface="lo",
        filter_expr="udp port 9999",
        target_pcap_path="/tmp/example_app_capture.pcap",
        snapshot_length=256,
        extra_args=["--dont-verify-checksums"],
    ) as cap:
        time.sleep(0.3)

        # Fire a UDP datagram — no listener required.
        target.exec(
            ["/example-app", "--udp-port", "9999", "--payload", payload],
            detach=False,
        )
        time.sleep(0.5)

    assert cap.target_path == "/tmp/example_app_capture.pcap"
    assert os.path.exists(cap.host_path), "Pcap file was not created"

    with open(cap.host_path, "rb") as f:
        pcap_data = f.read()
    assert payload.encode() in pcap_data, (
        f"Expected payload {payload!r} not found in captured pcap data"
    )

    os.unlink(cap.host_path)
