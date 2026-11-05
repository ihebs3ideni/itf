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
from score.itf.packs.dlt.framing import decode_message, encode_message


def test_encode_decode_round_trip():
    data = encode_message(ecu_id="GWAY", apid="APP1", ctid="CTX1", counter=7, payload=b"hello world")
    message, rest = decode_message(data)
    assert rest == b""
    assert (message.ecu_id, message.apid, message.ctid, message.counter) == ("GWAY", "APP1", "CTX1", 7)
    assert message.text() == "hello world"


def test_decode_returns_none_on_an_incomplete_buffer():
    data = encode_message(ecu_id="GWAY", apid="APP1", ctid="CTX1", counter=1, payload=b"x" * 50)
    message, rest = decode_message(data[:5])
    assert message is None
    assert rest == data[:5]


def test_decode_splits_two_concatenated_messages():
    first = encode_message(ecu_id="GWAY", apid="A1", ctid="C1", counter=1, payload=b"one")
    second = encode_message(ecu_id="GWAY", apid="A2", ctid="C2", counter=2, payload=b"two")
    buf = first + second

    m1, buf = decode_message(buf)
    m2, buf = decode_message(buf)

    assert (m1.apid, m1.text()) == ("A1", "one")
    assert (m2.apid, m2.text()) == ("A2", "two")
    assert buf == b""


def test_counter_wraps_at_one_byte():
    data = encode_message(ecu_id="GWAY", apid="A1", ctid="C1", counter=300, payload=b"x")
    message, _rest = decode_message(data)
    assert message.counter == 300 % 256
