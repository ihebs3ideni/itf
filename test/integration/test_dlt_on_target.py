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
import shlex
import time

from score.itf.plugins.capabilities.dlt.dlt_receive import Protocol


SECRET = "dlt_on_target_secret_payload"


def send_dlt_message(exec_interface, message):
    exec_interface.execute(f'/bin/sh -c "echo -n {shlex.quote(message)} | /usr/bin/dlt-adaptor-stdin"')


def test_dlt_on_target_tcp(exec_interface, dlt_on_target):
    """Receive a DLT message via TCP using dlt-receive running on the target."""
    with exec_interface.wrap_exec("/usr/bin/dlt-daemon"):
        time.sleep(1)

        with dlt_on_target(Protocol.TCP) as receiver:
            send_dlt_message(exec_interface, SECRET)
            time.sleep(1)

        output = receiver.get_output()
        assert SECRET in output, "Expected DLT message was not received via TCP"
        assert receiver.dlt_file is not None, "dlt_file path should be set"
        exit_code, _ = exec_interface.execute(f"test -f {receiver.dlt_file}")
        assert exit_code == 0, f"DLT file {receiver.dlt_file} was not created on target"


def test_dlt_on_target_udp(exec_interface, dlt_on_target):
    """Receive a DLT message via UDP multicast using dlt-receive on the target."""
    with exec_interface.wrap_exec("/usr/bin/dlt-daemon"):
        time.sleep(1)

        with dlt_on_target(Protocol.UDP, multicast_ips=["224.0.0.1"]) as receiver:
            send_dlt_message(exec_interface, SECRET)
            time.sleep(1)

        output = receiver.get_output()
        assert SECRET in output, "Expected DLT message was not received via UDP"


def test_dlt_on_target_multiple_receivers(exec_interface, dlt_on_target):
    """Multiple receivers can be started from the same fixture invocation."""
    with exec_interface.wrap_exec("/usr/bin/dlt-daemon"):
        time.sleep(1)

        with (
            dlt_on_target(Protocol.TCP) as tcp_receiver,
            dlt_on_target(Protocol.UDP, multicast_ips=["224.0.0.1"]) as udp_receiver,
        ):
            send_dlt_message(exec_interface, SECRET)
            time.sleep(1)

        assert SECRET in tcp_receiver.get_output(), "TCP receiver did not capture the message"
        assert SECRET in udp_receiver.get_output(), "UDP receiver did not capture the message"


def test_dlt_on_target_teardown_stops_receivers(exec_interface, dlt_on_target):
    """Receivers are stopped automatically when the context manager exits."""
    with exec_interface.wrap_exec("/usr/bin/dlt-daemon"):
        time.sleep(1)

        with dlt_on_target(Protocol.TCP) as receiver:
            assert receiver.is_running(), "Receiver should be running after start"

        assert not receiver.is_running(), "Receiver should be stopped after context exit"


def test_dlt_on_target_custom_output_file(exec_interface, dlt_on_target):
    """A custom output_file path is used when specified."""
    custom_path = "/tmp/custom_trace.dlt"
    with exec_interface.wrap_exec("/usr/bin/dlt-daemon"):
        time.sleep(1)

        with dlt_on_target(Protocol.TCP, output_file=custom_path) as receiver:
            send_dlt_message(exec_interface, SECRET)
            time.sleep(1)

        assert receiver.dlt_file == custom_path
        exit_code, _ = exec_interface.execute(f"test -f {custom_path}")
        assert exit_code == 0, f"DLT file was not created at custom path {custom_path}"
