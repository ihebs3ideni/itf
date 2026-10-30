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
"""Structured logging: every phase logs through `logging.getLogger("score.itf.core")`, so any runner
picks up a formatted, filterable trace of a session by attaching a handler to that name — no code
change, no new API to learn, whatever the runner already uses for its own logging.

Two things make this different from OCTO's diagnostics (`octo/diagnostics.py`), deliberately:
this layer *runs* things, not just resolves them, so it has a human (or a log aggregator) in front
of it the way OCTO never does — a readable `msg` is appropriate here, where OCTO's diagnostics have
none (`10-spec-octo-core.md` §13). Every field a structured/JSON formatter might want is still in
`extra={"itf_event": {...}}`, never only parseable out of the message text, so a consumer is never
forced to parse prose to get `step`, `scope`, `ok`, or `error` back out.

This is the default `observer` `Session` wires into `execute()`/`observe()` (`engine/bringup.py`)
— those functions stay logging-agnostic, taking a plain callback, same as before this existed.
"""

from __future__ import annotations

import logging

from .scopes import ROOT, display, display_json

logger = logging.getLogger("score.itf.core")
logger.addHandler(logging.NullHandler())  # a library emits; the runner decides whether anything lands


def _emit(level: int, msg: str, kind: str, **fields) -> None:
    logger.log(level, display(msg), extra={"itf_event": {"kind": kind, **display_json(fields)}})


# ---------------------------------------------------------------- bring-up (execute/observe) events


def log_event(kind: str, data: dict) -> None:
    """The `observer(kind, data)` callback `execute()`/`observe()` already call per event."""
    step = data.get("step") or data.get("ref") or ""
    if kind == "action_started":
        _emit(logging.INFO, f"{step}: starting", kind, **data)
    elif kind == "action_finished":
        ok = data.get("ok")
        level = logging.INFO if ok else logging.ERROR
        msg = f"{step}: ok" if ok else f"{step}: failed — {data.get('error')}"
        _emit(level, msg, kind, **data)
    elif kind == "action_skipped":
        _emit(logging.INFO, f"{step}: skipped ({data.get('reason')})", kind, **data)
    elif kind == "state_probed":
        if "error" in data:
            _emit(logging.WARNING, f"{step}: probe raised {data['error']}", kind, **data)
        else:
            level = logging.DEBUG if data.get("ok") else logging.WARNING
            _emit(level, f"{step}: probe {'held' if data.get('ok') else 'did not hold'}", kind, **data)
    elif kind == "node_realized":
        _emit(logging.DEBUG, f"{data.get('ref')}: realized", kind, **data)
    else:
        _emit(logging.DEBUG, f"{kind}: {data}", kind, **data)


# ---------------------------------------------------------------- session-level phase summaries


def log_phase(title: str) -> None:
    """A pytest-style section banner marking the start of a session phase."""
    _emit(logging.INFO, f"{'=' * 12} itf: {title} {'=' * 12}", "phase", title=title)


def log_target_summary(target_plan) -> None:
    """One aggregate line per scope: node/derived counts and tokens. Never the full node or seam
    list — `plan.json` already has that (docs/octo-kit/12-spec-itf-core.md §9); this is for a human
    scanning the log, not a replacement for the artifact."""
    for scope in target_plan.scopes():
        nodes = [n for n in target_plan.nodes if n.scope == scope]
        derived = sum(1 for n in nodes if n.derived)
        tokens = target_plan.tokens(scope)
        label = display(scope) if scope == ROOT else f"target.{scope}"
        _emit(
            logging.INFO,
            f"{label}: {len(nodes)} node(s) ({derived} derived) \u2014 tokens: {', '.join(tokens)}",
            "target_summary",
            scope=display(scope),
            nodes=len(nodes),
            derived=derived,
            tokens=list(tokens),
        )


def log_config_issues(issues) -> None:
    for ref, provider, message in issues:
        _emit(
            logging.ERROR,
            f"{ref} ({provider}): {message}",
            "config_invalid",
            ref=ref,
            provider=provider,
            message=message,
        )


def log_resolution(gate: int, hook: str, ok: bool, diagnostics) -> None:
    if ok:
        _emit(logging.INFO, f"Gate {gate} ({hook}): resolved", "gate_resolved", gate=gate, hook=hook)
    else:
        codes = [d.code for d in diagnostics]
        _emit(
            logging.ERROR,
            f"Gate {gate} ({hook}): failed — {', '.join(codes)}",
            "gate_failed",
            gate=gate,
            hook=hook,
            codes=codes,
        )


def log_gating(decisions: dict) -> None:
    for test_id, decision in decisions.items():
        if decision.selected:
            _emit(logging.DEBUG, f"{test_id}: selected", "gating_selected", test=test_id)
        else:
            _emit(
                logging.INFO,
                f"{test_id}: deselected \u2014 {decision.reason}",
                "gating_deselected",
                test=test_id,
                reason=decision.reason,
            )


def log_checks(results) -> None:
    for c in results:
        if c.ok:
            _emit(logging.INFO, f"startup check {c.name}: ok", "check_ok", name=c.name)
        else:
            level = logging.ERROR if c.essential else logging.WARNING
            _emit(
                level,
                f"startup check {c.name}: failed — {c.detail}",
                "check_failed",
                name=c.name,
                detail=c.detail,
                essential=c.essential,
            )


def log_teardown(results) -> None:
    for name, ok, error in results:
        if ok:
            _emit(logging.INFO, f"teardown hook {name}: ok", "teardown_ok", name=name)
        else:
            _emit(logging.ERROR, f"teardown hook {name}: failed — {error}", "teardown_failed", name=name, error=error)


def log_drift(entry: dict) -> None:
    """A re-probe disagrees with what execution tracked: something changed a state undeclared."""
    parts = [f"{k} {', '.join(entry[k])}" for k in ("dropped", "appeared") if entry[k]]
    _emit(logging.WARNING, f"drift {entry['phase']}: {'; '.join(parts)}", "drift", **entry)


def log_unwind(report) -> None:
    if report.kept:
        _emit(logging.INFO, "unwind: kept (on_exit=keep)", "unwind_kept")
        return
    for ref in report.dismantled:
        _emit(logging.DEBUG, f"{ref}: dismantled", "unwind_dismantled", ref=ref)
    for ref, error in report.errors:
        _emit(logging.ERROR, f"{ref}: failed to dismantle — {error}", "unwind_error", ref=ref, error=error)
    _emit(
        logging.INFO,
        f"unwind: {len(report.dismantled)} dismantled, {len(report.errors)} error(s)",
        "unwind_done",
        dismantled=len(report.dismantled),
        errors=len(report.errors),
    )
