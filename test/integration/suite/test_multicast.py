"""Project-framed DLT over UDP multicast, without a guest DLT daemon."""

import time
from pathlib import Path
from typing import Protocol
from uuid import uuid4

import score.itf as itf


class Message(Protocol):
    ecu_id: str
    apid: str
    ctid: str
    counter: int

    def text(self) -> str: ...


class StreamingLogs(Protocol):
    __contract__ = "observe.logs"

    def lines(self) -> list[Message]: ...


class MulticastLogs(Protocol):
    __contract__ = "observe.logs"

    def is_active(self) -> bool: ...
    def filter(
        self, *, apid: str | None = None, ctid: str | None = None, ecu_id: str | None = None
    ) -> list[Message]: ...
    def count(self) -> int: ...
    def path(self) -> Path | None: ...
    def dropped_bytes(self) -> int: ...


class Traffic(Protocol):
    __contract__ = "integration.traffic"

    def send_dlt(self, text: str, /) -> None: ...


class CountedTraffic(Protocol):
    __contract__ = "integration.traffic"

    def send_dlt(self, text: str, /, *, counter: int) -> None: ...


class GroupTraffic(Protocol):
    __contract__ = "integration.traffic"

    def send_dlt(self, text: str, /, *, group: str) -> None: ...


itf_requires = [
    itf.requires("logs", shape=StreamingLogs),
    itf.requires("traffic", shape=Traffic),
]


@itf.requires("logs", shape=MulticastLogs)
@itf.requires("traffic", shape=CountedTraffic)
def test_multicast_decodes_ids_and_persists_the_message(target):
    logs = target.logs
    assert logs.is_active()
    path = logs.path()
    assert path is not None, "configure logs.dlt_file for multicast evidence"
    token = f"itf-multicast-{uuid4().hex}"
    before_count, before_dropped = logs.count(), logs.dropped_bytes()
    target.traffic.send_dlt(token, counter=73)
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        matches = [message for message in logs.lines() if token in message.text()]
        if matches and path.is_file() and token.encode("ascii") in path.read_bytes():
            break
        time.sleep(0.05)
    else:
        raise AssertionError(f"DLT payload {token!r} was not decoded and persisted at {path}")
    assert all(
        (message.ecu_id, message.apid, message.ctid, message.counter) == ("ECU1", "ITF1", "UDP1", 73)
        for message in matches
    )
    assert any(token in message.text() for message in logs.filter(ecu_id="ECU1", apid="ITF1", ctid="UDP1"))
    assert not any(token in message.text() for message in logs.filter(ecu_id="NONE"))
    assert not any(token in message.text() for message in logs.filter(apid="NONE"))
    assert not any(token in message.text() for message in logs.filter(ctid="NONE"))
    assert logs.count() >= before_count + 1
    assert logs.dropped_bytes() == before_dropped
    assert b"DLT\x01" in path.read_bytes()


@itf.requires("traffic", shape=GroupTraffic)
def test_unjoined_multicast_groups_do_not_enter_the_log_stream(target):
    excluded = "unjoined-" + uuid4().hex
    sentinel = "subscribed-" + uuid4().hex
    target.traffic.send_dlt(excluded, group="239.255.42.100")
    target.traffic.send_dlt(sentinel)
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        messages = target.logs.lines()
        if any(sentinel in message.text() for message in messages):
            assert not any(excluded in message.text() for message in messages)
            return
        time.sleep(0.05)
    raise AssertionError("the subscribed multicast sentinel did not arrive")
