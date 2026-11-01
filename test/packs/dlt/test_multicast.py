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
import socket
import struct
import time

import pytest

from score.itf.packs.dlt.multicast.receiver import (
    MulticastDltReceiver,
    parse_sources,
    split_datagram,
)
from score.itf.packs.dlt.multicast.providers import make_multicast
from score.itf.packs.dlt.multicast.steps import is_joined, join_multicast
from score.itf.packs.dlt.framing import encode_message


def message(text, counter=0, ecu_id="ISOC", apid="APP", ctid="CTX"):
    return encode_message(ecu_id=ecu_id, apid=apid, ctid=ctid, counter=counter, payload=text.encode())


def wait_until(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, "condition not reached"
        time.sleep(0.01)


def test_parse_sources_matches_legacy_datarouter_layout():
    sources = parse_sources("160.48.249.125=224.127.42.99,224.255.42.99; 160.48.199.205=228.127.42.88")
    assert sources == [("160.48.249.125", ["224.127.42.99", "224.255.42.99"]), ("160.48.199.205", ["228.127.42.88"])]
    assert parse_sources("127.0.0.1=") == [("127.0.0.1", [])]


@pytest.mark.parametrize("text", ["", "not-ip=224.0.0.1", "127.0.0.1=10.0.0.1"])
def test_parse_sources_rejects_invalid(text):
    with pytest.raises(ValueError):
        parse_sources(text)


def test_split_datagram_handles_batches_and_truncation():
    found, dropped = split_datagram(message("a") + message("bb", 1) + b"\x35\x00\x00\x40")
    assert [m.text() for _, m in found] == ["a", "bb"]
    assert dropped == 4


def test_construction_is_inert_and_probe_false():
    receiver = MulticastDltReceiver("127.0.0.1=", port=0)
    assert is_joined(receiver) is False
    with pytest.raises(RuntimeError, match="not active"):
        receiver.lines()
    receiver.close()


def test_receives_filters_and_writes_storage_format(tmp_path):
    out = tmp_path / "dlt" / "boot.dlt"
    receiver = MulticastDltReceiver("127.0.0.1=", port=0, dlt_file=str(out))
    join_multicast(receiver)
    assert is_joined(receiver)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
        target = ("127.0.0.1", receiver.bound_port())
        sender.sendto(message("boot ok") + message("hello", 1, ecu_id="CNSO"), target)
        sender.sendto(b"\x01\x02", target)
    wait_until(lambda: receiver.count() == 2 and receiver.dropped_bytes() == 2)
    assert [m.text() for m in receiver.filter(ecu_id="CNSO")] == ["hello"]
    assert receiver.filter(apid="APP")[0].text() == "boot ok"
    receiver.close()
    data = out.read_bytes()
    assert data.startswith(b"DLT\x01") and data.count(b"DLT\x01") == 2
    assert data[12:16] == b"ISOC" and data[16:].startswith(message("boot ok"))
    seconds = struct.unpack("<I", data[4:8])[0]
    assert abs(seconds - time.time()) < 60


def test_provider_teardown_closes_receiver(tmp_path):
    provider = make_multicast({"sources": "127.0.0.1=", "port": 0})
    receiver = next(provider)
    receiver.subscribe()
    with pytest.raises(StopIteration):
        next(provider)
    assert not receiver.active()
