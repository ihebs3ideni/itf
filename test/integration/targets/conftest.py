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
"""The project's own code, shared by every integration composition: the bench-local actions the DLT
compositions choose with `by:`, and readiness checks, written against roles (`command`, `console`, `platform`,
`process`). The composition itself is configured (`ITF_TARGET`, or `py_itf_test(target = ...)`), not loaded here.
"""

import logging
import os
from pathlib import Path
from typing import Protocol

import pytest

from score.itf.core import hookimpl, state

log = logging.getLogger("integration")
EVIDENCE = Path(os.environ.get("TEST_UNDECLARED_OUTPUTS_DIR", ".")) / "evidence"
_daemon: dict = {}


@hookimpl
def itf_verify(session):
    """Readiness, checked once after bring-up: a target that cannot answer fails here with a named check."""
    target = session.target
    log.info("verify: target offers %s", ", ".join(sorted(target.names())))
    if target.has("command"):
        code, output = target.command.exec("echo -n ready")
        session.check(
            "command.answers", code == 0 and output.strip().endswith("ready"), detail=f"exit {code}, {output!r}"
        )
    if target.has("platform"):
        session.check("platform.running", target.platform.running())


@hookimpl
def itf_teardown(session):
    """Evidence, collected while the target still runs: console transcript and container output."""
    target = session.target
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    if target.has("console"):
        path = EVIDENCE / "console.txt"
        path.write_text("\n".join(target.console.lines()), encoding="utf-8")
        log.info("teardown: console transcript (%d lines) saved to %s", len(target.console.lines()), path)
    container = getattr(target.platform, "container", None) if target.has("platform") else None
    if container is not None:
        path = EVIDENCE / "container.log"
        path.write_bytes(container.logs())
        log.info("teardown: container output saved to %s", path)


@pytest.fixture(autouse=True)
def _narrate(request):
    """One INFO line per scenario, so the log reads as a story (details stay at DEBUG)."""
    log.info("scenario: %s", request.node.name.removeprefix("test_").replace("_", " "))
    yield


def pytest_runtest_logreport(report):
    if report.when == "call" or report.outcome == "skipped":
        log.info("verdict: %s %s", report.nodeid.split("::")[-1], report.outcome)


class Process(Protocol):
    __contract__ = "exec.process"

    def spawn(self, binary_path: str, args: list[str] | None = None, cwd: str = "/"): ...


class Logs(Protocol):
    __contract__ = "observe.logs"

    def subscribe(self) -> None: ...


@state("bench.dlt_daemon.running", after=("platform.up",), label="start_dlt_daemon")
def start_dlt_daemon(process: Process):
    _daemon["handle"] = process.spawn("/usr/bin/dlt-daemon")


@start_dlt_daemon.probe
def dlt_daemon_running(process: Process):
    return "handle" in _daemon and _daemon["handle"].is_running()


@state("logs.active", after=("bench.dlt_daemon.running",), label="activate_logs")
def activate_logs(logs: Logs):
    """Subscribe once the daemon runs: the DLT packs' own actions do not wait for a daemon this bench starts."""
    logs.subscribe()


@activate_logs.probe
def logs_active(logs: Logs):
    check = getattr(logs, "active", None) or logs._live
    return check()
