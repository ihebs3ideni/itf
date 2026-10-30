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
"""Structured logging (`score.itf.core/engine/log.py`): every phase logs through
`logging.getLogger("score.itf.core")`, with structured fields under `extra["itf_event"]`, so any runner
picks it up by attaching a handler — no code change, no new API to learn."""

from __future__ import annotations

import logging

from score.itf.core.session import Session


def _events(records, kind=None):
    out = [r.itf_event for r in records if hasattr(r, "itf_event")]
    return [e for e in out if kind is None or e["kind"] == kind]


def test_resolve_logs_gate_1_and_gate_2_success(caplog, tmp_path):
    caplog.set_level(logging.DEBUG, logger="score.itf.core")
    Session(["shell_recipe"], run_dir=tmp_path).resolve()

    resolved = _events(caplog.records, "gate_resolved")
    assert {(e["gate"], e["hook"]) for e in resolved} == {(1, "itf_setup"), (2, "itf_init")}


def test_resolve_logs_a_phase_divider_and_target_summary(caplog, tmp_path):
    caplog.set_level(logging.DEBUG, logger="score.itf.core")
    Session(["shell_recipe"], run_dir=tmp_path).resolve()

    phases = {e["title"] for e in _events(caplog.records, "phase")}
    assert "resolve" in phases

    summaries = _events(caplog.records, "target_summary")
    assert summaries, "expected a target_summary event"
    assert summaries[0]["scope"] == "main"
    assert summaries[0]["nodes"] >= 1
    assert "tokens" in summaries[0]


def test_resolve_logs_gate_failure_with_diagnostic_codes(caplog, tmp_path):
    caplog.set_level(logging.DEBUG, logger="score.itf.core")
    session = Session(["broken_recipe"], run_dir=tmp_path)
    try:
        session.resolve()
    except Exception:
        pass

    failed = _events(caplog.records, "gate_failed")
    assert failed, "expected a gate_failed event"
    assert failed[0]["codes"]


def test_bring_up_logs_action_lifecycle(caplog, tmp_path):
    caplog.set_level(logging.DEBUG, logger="score.itf.core")
    session = Session(["shell_recipe"], run_dir=tmp_path)
    session.resolve()
    session.bring_up()
    try:
        started = {e["step"] for e in _events(caplog.records, "action_started")}
        finished = {e["step"]: e["ok"] for e in _events(caplog.records, "action_finished")}
        assert "main:itf.states.shell.open" in started
        assert finished.get("main:itf.states.shell.open") is True
        assert all(ok for ok in finished.values())
        phases = {e["title"] for e in _events(caplog.records, "phase")}
        assert {"bring-up", "startup checks"} <= phases
    finally:
        session.close()


def test_close_logs_unwind_summary(caplog, tmp_path):
    session = Session(["shell_recipe"], run_dir=tmp_path)
    session.resolve()
    session.bring_up()
    caplog.clear()
    caplog.set_level(logging.DEBUG, logger="score.itf.core")
    session.close()

    phases = {e["title"] for e in _events(caplog.records, "phase")}
    assert "close" in phases

    done = _events(caplog.records, "unwind_done")
    assert len(done) == 1
    assert done[0]["errors"] == 0


def test_select_logs_deselection_with_reason(caplog, tmp_path):
    from score.itf.core import gating

    caplog.set_level(logging.DEBUG, logger="score.itf.core")
    session = Session(["shell_recipe"], run_dir=tmp_path)
    session.resolve()
    req = gating.Requirement(token="nonexistent.token")
    session.select({"test_x": (req,)})

    deselected = _events(caplog.records, "gating_deselected")
    assert any(e["test"] == "test_x" and e["reason"] for e in deselected)


def test_no_handler_does_not_raise():
    """A library emits; with zero handlers configured, nothing should error (NullHandler)."""
    from score.itf.core.engine.log import logger as itf_logger

    assert any(isinstance(h, logging.NullHandler) for h in itf_logger.handlers)
