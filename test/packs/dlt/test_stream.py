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
import threading
import time

from score.itf.packs.dlt.framing import encode_message
from score.itf.packs.dlt.stream import DltReceiver


class _Endpoint:
    def __init__(self, host, port):
        self.host = host
        self.port = port


def _serve_once(server: socket.socket, payload: bytes, stop: threading.Event) -> None:
    server.settimeout(5)
    conn, _addr = server.accept()
    with conn:
        conn.sendall(payload)
        while not stop.is_set():
            time.sleep(0.02)


def test_dlt_receiver_parses_frames_from_a_real_tcp_socket():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    host, port = server.getsockname()

    payload = encode_message(ecu_id="GWAY", apid="APP1", ctid="CTX1", counter=1, payload=b"started") + encode_message(
        ecu_id="GWAY", apid="APP1", ctid="CTX1", counter=2, payload=b"running"
    )
    stop = threading.Event()
    server_thread = threading.Thread(target=_serve_once, args=(server, payload, stop), daemon=True)
    server_thread.start()

    receiver = DltReceiver(_Endpoint(host, port), ecu_id="GWAY")
    receiver.subscribe()
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and len(receiver.lines()) < 2:
            time.sleep(0.02)
        messages = receiver.lines()
        assert [m.text() for m in messages] == ["started", "running"]
        assert receiver.filter(apid="APP1") == messages
        assert receiver.filter(apid="NOPE") == []
        assert receiver._live() is True
    finally:
        stop.set()
        receiver.close()
        server.close()
        server_thread.join(timeout=2)

    assert receiver._live() is False


def test_lines_raises_once_closed():
    receiver = DltReceiver(_Endpoint("127.0.0.1", 1), ecu_id="GWAY")
    try:
        import pytest

        with pytest.raises(RuntimeError):
            receiver.lines()
    finally:
        receiver.close()
