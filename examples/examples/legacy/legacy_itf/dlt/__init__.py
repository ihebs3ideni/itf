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
"""ITF's original DLT classes, presented over the composition's `logs` role (`dlt.receive`).

Both open a bounded recording (`window()`) aimed where the caller says: protocol, interface,
target and multicast groups are per-call arguments, as they were. The binary path belongs to the
composition and is ignored here.
"""

import logging
from enum import Enum, auto

LOGS = "observe.logs"
DEFAULT_LOGGER = "dlt_receive_window"
_session = {}


class Protocol(Enum):
    TCP = auto()
    UDP = auto()


def bind(session) -> None:
    """Called by the conftest: the session whose logs node these classes use."""
    _session["session"] = session


def _logs():
    session = _session.get("session")
    if session is None:
        raise RuntimeError("legacy DLT helpers are not bound to a session")
    names = sorted(n["name"] for n in session.target.plan()["target"]["nodes"] if n["contract"] == LOGS)
    if not names:
        raise NotImplementedError("the composition has no logs role: pass --dlt-receive-path or --dlt-config")
    return session.target.get(names[0])


def _route(protocol, host_ip, target_ip, multicast_ips) -> dict:
    from enum import Enum as _Enum  # the pack's transport enum is reached by member name, never imported

    node_transport = type(_logs().transport)
    return {
        "transport": node_transport[protocol.name] if isinstance(protocol, _Enum) else None,
        "host_ip": host_ip,
        "target_ip": target_ip,
        "multicast_ips": multicast_ips,
    }


class _Frame:
    """A message in the original shape: `payload` is text."""

    def __init__(self, message):
        self.time_stamp, self.apid, self.ctid, self.raw_msg = (
            message.time_stamp,
            message.apid,
            message.ctid,
            message.raw,
        )
        self.payload = message.text()


class _Record:
    def __init__(self, record):
        self._record = record

    def find(self, *args, **kwargs):
        return [_Frame(m) for m in self._record.find(*args, **kwargs)]

    def __getattr__(self, name):
        return getattr(self._record, name)


class DltWindow:
    """A bounded recording for a `with` block, queried with `record()` (python-dlt `find`)."""

    def __init__(
        self,
        protocol=Protocol.UDP,
        host_ip=None,
        multicast_ips=None,
        target_ip=None,
        file_name=None,
        print_to_stdout=False,
        logger_name=None,
        dlt_filter=None,
        binary_path=None,
    ):
        self._route = _route(protocol, host_ip, target_ip, multicast_ips)
        self._filter, self._print = dlt_filter, print_to_stdout
        self._logger = logger_name or DEFAULT_LOGGER
        self._captured = []
        self._handler = logging.Handler()
        self._handler.emit = lambda record: self._captured.append(self._handler.format(record))
        self._handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
        self._window = self._recorder = None

    def __enter__(self):
        logging.getLogger(self._logger).addHandler(self._handler)
        self._window = _logs().window(
            dlt_filter=self._filter, print_to_stdout=self._print, logger_name=self._logger, **self._route
        )
        self._recorder = self._window.__enter__()
        return self

    def __exit__(self, *exc):
        self._window.__exit__(*exc)
        logging.getLogger(self._logger).removeHandler(self._handler)
        return False

    def record(self, filters=None):
        return _Record(self._recorder.record(filters))

    def file_name(self):
        return self._recorder.file_name

    def get_logged_output(self, clear_after_read=False):
        output = "\n".join(self._captured)
        if clear_after_read:
            self._captured.clear()
        return output

    def get_captured_logs(self):
        return self._captured


class DltReceive(DltWindow):
    """A recording whose output is logged (and optionally written to the log) while the block runs;
    called without a transport (the `dlt` session fixture) it records with the node's own."""

    def __init__(
        self,
        protocol=Protocol.UDP,
        host_ip=None,
        multicast_ips=None,
        target_ip=None,
        file_name=None,
        enable_file_output=True,
        print_to_stdout=False,
        logger_name=None,
        binary_path=None,
    ):
        super().__init__(
            protocol, host_ip, multicast_ips, target_ip, file_name, print_to_stdout, logger_name, None, binary_path
        )
