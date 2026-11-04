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
"""dlt-receive arguments: the node's transport, and a per-recording override (window())."""

from types import SimpleNamespace

from score.itf.packs.dlt.receive.tool import DltReceive, Transport


def _udp():
    return DltReceive({"host_ip": "127.0.0.1", "multicast_ips": "224.0.0.1", "binary_path": "dlt-receive"})


def _tcp():
    return DltReceive({"binary_path": "dlt-receive"}, SimpleNamespace(host="10.0.0.5"))


def test_a_udp_node_joins_its_groups_on_its_interface():
    args = _udp()._arguments("out.dlt", False)
    assert args == ["-o", "out.dlt", "--udp", "--net-if", "127.0.0.1", "--port", "3490", "--mcast-ip", "224.0.0.1"]


def test_a_tcp_node_connects_to_its_endpoint():
    assert _tcp()._arguments("out.dlt", False) == ["-o", "out.dlt", "--tcp", "10.0.0.5"]


def test_a_route_aims_one_recording_elsewhere_without_touching_the_node():
    node = _udp()
    args = node._arguments("w.dlt", True, route={"transport": Transport.TCP, "target_ip": "172.17.0.2"})
    assert args == ["-o", "w.dlt", "--tcp", "172.17.0.2", "-a", "--stdout-flush"]
    args = node._arguments("w.dlt", False, route={"host_ip": "172.17.0.1", "multicast_ips": ["239.1.1.1"]})
    assert args[-4:] == ["--port", "3490", "--mcast-ip", "239.1.1.1"] and "172.17.0.1" in args
    assert node._arguments("w.dlt", False) == [
        "-o",
        "w.dlt",
        "--udp",
        "--net-if",
        "127.0.0.1",
        "--port",
        "3490",
        "--mcast-ip",
        "224.0.0.1",
    ]
