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
"""The legacy DLT classes aim a recording where the caller says, and return the original frame shape.
No container: a fake logs node records what `window()` is asked for."""

from contextlib import contextmanager
from enum import Enum, auto
from types import SimpleNamespace

import pytest

from legacy_itf import dlt as legacy_dlt
from legacy_itf.dlt import DltReceive, DltWindow, Protocol


class _Transport(Enum):
    TCP = auto()
    UDP = auto()


class _Message:
    time_stamp, apid, ctid, raw = 1.0, "SINA", "SINC", object()

    def text(self):
        return "This is a secret message"


class _Recorder:
    file_name = "/tmp/fake.dlt"

    def record(self, filters=None):
        return SimpleNamespace(find=lambda *a, **k: [_Message()], total_count=lambda: 1)


class _Logs:
    transport = _Transport.UDP

    def __init__(self):
        self.asked = None

    @contextmanager
    def window(self, **asked):
        self.asked = asked
        yield _Recorder()


@pytest.fixture
def logs():
    node = _Logs()
    plan = {"target": {"nodes": [{"name": "logs", "contract": legacy_dlt.LOGS}]}}
    legacy_dlt.bind(SimpleNamespace(target=SimpleNamespace(plan=lambda: plan, get=lambda name: node)))
    return node


def test_a_window_is_aimed_with_the_protocol_and_addresses_the_caller_passed(logs):
    with DltWindow(
        Protocol.TCP,
        host_ip="10.0.0.1",
        target_ip="10.0.0.2",
        multicast_ips=["224.0.0.1"],
        logger_name="mine",
        print_to_stdout=True,
        dlt_filter="APID CTID",
    ):
        pass
    assert logs.asked == {
        "dlt_filter": "APID CTID",
        "print_to_stdout": True,
        "logger_name": "mine",
        "transport": _Transport.TCP,
        "host_ip": "10.0.0.1",
        "target_ip": "10.0.0.2",
        "multicast_ips": ["224.0.0.1"],
    }


def test_a_receive_without_arguments_uses_udp_and_the_default_logger(logs):
    with DltReceive():
        pass
    assert logs.asked["transport"] is _Transport.UDP and logs.asked["logger_name"] == legacy_dlt.DEFAULT_LOGGER


def test_found_frames_carry_text_payloads_like_the_original(logs):
    with DltWindow() as window:
        frames = window.record().find()
    assert "This is a secret message" in frames[0].payload and frames[0].apid == "SINA"
