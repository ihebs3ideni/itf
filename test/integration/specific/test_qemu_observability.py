"""Renew a managed platform and observe fresh traffic through its restored goals."""

import subprocess
import time
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Protocol
from uuid import uuid4

import pytest

import score.itf as itf


class Platform(Protocol):
    __contract__ = "platform.instance"

    def running(self) -> bool: ...


class Capture(Protocol):
    __contract__ = "observe.capture"

    def running(self) -> bool: ...
    def window(self, name: str, *, ready_timeout: float = 5.0) -> AbstractContextManager[Path]: ...


class PacketReader(Protocol):
    __contract__ = "integration.packet_reader"

    def read(self, path: Path) -> str: ...


class Message(Protocol):
    def text(self) -> str: ...


class Logs(Protocol):
    __contract__ = "observe.logs"

    def is_active(self) -> bool: ...
    def lines(self) -> list[Message]: ...


class Traffic(Protocol):
    __contract__ = "integration.traffic"
    host: str
    port: int

    def send(self, payload: bytes, host: str, port: int) -> None: ...
    def send_dlt(self, text: str, group: str | None = None, port: int | None = None, *, counter: int = 0) -> None: ...


@pytest.fixture
def observe_traffic(target):
    def observe(phase: str) -> None:
        assert target.platform.running()
        assert target.capture.running()
        assert target.logs.is_active()
        token = f"itf-renew-{phase}-{uuid4().hex}"
        with target.capture.window(token) as path:
            target.traffic.send(token.encode("ascii"), target.traffic.host, target.traffic.port)
            target.traffic.send_dlt(token)
            deadline = time.monotonic() + 8.0
            while time.monotonic() < deadline:
                try:
                    captured = token in target.packet_reader.read(path)
                except subprocess.CalledProcessError:
                    captured = False
                received = any(token in message.text() for message in target.logs.lines())
                if captured and received:
                    break
                time.sleep(0.05)
            else:
                raise AssertionError(f"network observability did not recover during {phase}")
        assert token in target.packet_reader.read(path)

    return observe


@itf.requires("platform", shape=Platform)
@itf.requires("capture", shape=Capture)
@itf.requires("packet_reader", shape=PacketReader)
@itf.requires("logs", shape=Logs)
@itf.requires("traffic", shape=Traffic)
def test_renew_platform_restores_network_observability(target, observe_traffic):
    observe_traffic("before")
    target.renew("platform")
    observe_traffic("after")
