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
"""DLT through the dlt-receive tool, recorded to a file and queried with python-dlt (ITF's
`DltReceive`/`DltWindow`). The tool is built by Bazel and shipped beside the pack."""

from __future__ import annotations

import logging
import os
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum, auto
from typing import Protocol
from score.itf.core.process import ProcessWrapper

logger = logging.getLogger(__name__)


DLT_PORT = "3490"


class Transport(Enum):
    TCP = auto()
    UDP = auto()


def protocol_arguments(
    transport: Transport, host_ip: str | None, target_ip: str | None, multicast_ips: list[str]
) -> list[str]:
    if transport == Transport.TCP:
        return ["--tcp", target_ip]
    if transport == Transport.UDP:
        multicast = [arg for ip in multicast_ips for arg in ("--mcast-ip", ip)]
        return ["--udp", "--net-if", host_ip, "--port", DLT_PORT, *multicast]
    raise RuntimeError(f"Unsupported transport {transport}; supported: {', '.join(t.name for t in Transport)}")


def bundled(name: str) -> str:
    """A file Bazel ships beside this module (dlt-receive), or `name` itself to search PATH."""
    try:
        from python.runfiles import runfiles
    except ImportError:
        return name
    located_files = runfiles.Create()
    located = located_files.Rlocation(f"score_itf/score/itf/packs/dlt/{name}") if located_files else None
    return located if located and os.path.exists(located) else name


def output_dir() -> str:
    return os.environ.get("TEST_UNDECLARED_OUTPUTS_DIR") or tempfile.gettempdir()


@dataclass(frozen=True)
class Message:
    ecu_id: str
    apid: str
    ctid: str
    payload: bytes
    time_stamp: float
    raw: object

    def text(self) -> str:
        return self.payload.decode("utf-8", errors="replace")


def _message(raw) -> Message:
    payload = getattr(raw, "payload_decoded", b"")
    if isinstance(payload, str):
        payload = payload.encode()
    return Message(
        ecu_id=str(getattr(raw, "ecuid", "") or ""),
        apid=str(raw.apid),
        ctid=str(raw.ctid),
        payload=payload or b"",
        time_stamp=getattr(raw, "tmsp", 0.0),
        raw=raw,
    )


class DltLogRecord:
    """Messages loaded from a recorded file; `filters` as python-dlt takes them: [("APID", "CTID"), ...]."""

    def __init__(self, file_name: str, filters=None):
        import dlt.dlt as python_dlt

        self._content = python_dlt.load(file_name, filters=filters)
        self._queried = 0

    def find(
        self,
        query: dict | None = None,
        include_ext: bool = True,
        include_non_ext: bool = False,
        full_match: bool = True,
        timeout: float | None = None,
    ) -> list[Message]:
        """Messages matching `query`, e.g. {"apid": re.compile(r"^A"), "payload_decoded": re.compile("up")}."""
        if not include_ext and not include_non_ext:
            logger.warning("Both include_ext and include_non_ext are False: empty search space")
            return []
        self._queried, result, started = 0, [], time.monotonic()
        for raw in self._content:
            if raw.use_extended_header and not include_ext or not raw.use_extended_header and not include_non_ext:
                continue
            self._queried += 1
            if not query or raw.compare(query):
                result.append(_message(raw))
                if not full_match:
                    break
            if timeout is not None and time.monotonic() - started >= timeout:
                break
        return result

    def total_count(self) -> int:
        return self._content.counter_total

    def filtered_count(self) -> int:
        return self._content.counter

    def queried_count(self) -> int:
        return self._queried


class Endpoint(Protocol):
    host: str


@dataclass(frozen=True)
class ReceiveConfig:
    host_ip: str = "127.0.0.1"
    multicast_ips: str = ""
    file_name: str | None = None
    print_to_stdout: bool = False
    binary_path: str | None = None


class DltReceive:
    """`itf.capabilities.observe.logs` through dlt-receive: UDP on `host_ip` joining `multicast_ips`,
    or TCP to an endpoint's host. Everything is recorded to `path()`."""

    def __init__(self, config: dict, endpoint: Endpoint | None = None):
        self.endpoint = endpoint
        self.transport = Transport.TCP if endpoint is not None else Transport.UDP
        self.host_ip = config.get("host_ip", "127.0.0.1")
        self.multicast_ips = [ip.strip() for ip in (config.get("multicast_ips") or "").split(",") if ip.strip()]
        self.file_name = config.get("file_name") or os.path.join(output_dir(), "dlt_receive.dlt")
        self.print_to_stdout = config.get("print_to_stdout", False)
        self.binary_path = config.get("binary_path") or bundled("dlt-receive")
        self._process: ProcessWrapper | None = None

    def _arguments(
        self, file_name: str, print_to_stdout: bool, filter_file: str | None = None, route: dict | None = None
    ) -> list[str]:
        """`route` overrides the node's transport for one recording: transport, host_ip, target_ip, multicast_ips."""
        route = route or {}
        target_ip = route.get("target_ip") or (self.endpoint.host if self.endpoint is not None else None)
        transport = route.get("transport") or self.transport
        args = [
            "-o",
            file_name,
            *protocol_arguments(
                transport,
                route.get("host_ip") or self.host_ip,
                target_ip,
                route["multicast_ips"] if route.get("multicast_ips") is not None else self.multicast_ips,
            ),
        ]
        args += ["-a", "--stdout-flush"] if print_to_stdout else []
        args += ["-f", filter_file] if filter_file else []
        return args

    def subscribe(self) -> None:
        if os.path.exists(self.file_name):
            os.remove(self.file_name)
        os.makedirs(os.path.dirname(self.file_name) or ".", exist_ok=True)
        self._process = ProcessWrapper(
            self.binary_path, self._arguments(self.file_name, self.print_to_stdout), logger_name="dlt_receive"
        )
        self._process.start_process()

    def active(self) -> bool:
        return self._process is not None and self._process.is_running()

    def close(self) -> None:
        if self._process is not None:
            self._process.kill_process()
            self._process = None

    def path(self) -> str:
        return self.file_name

    def record(self, filters=None) -> DltLogRecord:
        return DltLogRecord(self.file_name, filters)

    def lines(self) -> list[Message]:
        if not os.path.exists(self.file_name):
            return []
        return self.record().find()

    def filter(self, apid: str | None = None, ctid: str | None = None) -> list[Message]:
        return [m for m in self.lines() if (apid is None or m.apid == apid) and (ctid is None or m.ctid == ctid)]

    @contextmanager
    def window(
        self,
        dlt_filter: str | None = None,
        print_to_stdout: bool = False,
        *,
        transport: Transport | None = None,
        host_ip: str | None = None,
        target_ip: str | None = None,
        multicast_ips: list[str] | None = None,
        logger_name: str = "dlt_receive_window",
    ) -> Iterator[DltLogRecorder]:
        """A second dlt-receive for a `with` block, e.g. one test; `dlt_filter` like "APID CTID".
        `transport`, `host_ip`, `target_ip` and `multicast_ips` aim this recording elsewhere than the
        node (another interface, another target); its output goes to the `logger_name` logger."""
        route = {"transport": transport, "host_ip": host_ip, "target_ip": target_ip, "multicast_ips": multicast_ips}
        recorder = DltLogRecorder(self, dlt_filter, print_to_stdout, route, logger_name)
        recorder.start()
        try:
            yield recorder
        finally:
            recorder.stop()


class DltLogRecorder:
    """One bounded recording (ITF's `DltWindow`): `record()` loads what it captured."""

    def __init__(
        self,
        receive: DltReceive,
        dlt_filter: str | None,
        print_to_stdout: bool,
        route: dict | None = None,
        logger_name: str = "dlt_receive_window",
    ):
        handle, self.file_name = tempfile.mkstemp(suffix=".dlt", prefix="dlt_window_")
        os.close(handle)
        self._filter_file = None
        if dlt_filter:
            handle, self._filter_file = tempfile.mkstemp(suffix=".txt", prefix="dlt_filter_")
            with os.fdopen(handle, "w", encoding="utf-8") as f:
                f.write(f"{dlt_filter}\n\n")
        self._process = ProcessWrapper(
            receive.binary_path,
            receive._arguments(self.file_name, print_to_stdout, self._filter_file, route),
            logger_name=logger_name,
        )

    def start(self) -> None:
        self._process.start_process()

    def stop(self) -> None:
        self._process.kill_process()
        if self._filter_file and os.path.exists(self._filter_file):
            os.remove(self._filter_file)

    def record(self, filters=None) -> DltLogRecord:
        return DltLogRecord(self.file_name, filters)
