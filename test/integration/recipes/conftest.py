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
"""The policy every integration recipe shares.

Declarative half: the YAML recipe ITF_RECIPE names (a Starlark recipe given with
`py_itf_test(recipe = ...)` arrives through its own entrypoint instead, and then these two hooks
do nothing). Code half: a bench-local action for DLT recipes and readiness checks.
"""

import logging
import os
from pathlib import Path
from typing import Protocol

import pytest

from score.itf.core import delivers, hookimpl, load_init, load_setup

log = logging.getLogger("integration")
COMMAND = "itf.capabilities.exec.command"
CONSOLE = "itf.capabilities.exec.console"
EVIDENCE = Path(os.environ.get("TEST_UNDECLARED_OUTPUTS_DIR", ".")) / "evidence"
_RECIPE = os.environ.get("ITF_RECIPE")
_daemon: dict = {}


@hookimpl
def itf_setup(ctx):
    if _RECIPE:
        load_setup(ctx, Path(__file__).with_name(_RECIPE))


@hookimpl
def itf_init(ctx):
    if _RECIPE:
        load_init(ctx, Path(__file__).with_name(_RECIPE))


@hookimpl
def itf_verify(session):
    """Readiness, checked once after bring-up: a target that cannot answer fails here with a named check."""
    target = session.target
    log.info("verify: target offers %s", ", ".join(sorted(target.tokens())))
    if target.has(COMMAND):
        code, output = target.command.exec("echo -n ready")
        session.check(
            "command.answers", code == 0 and output.strip().endswith("ready"), detail=f"exit {code}, {output!r}"
        )
    if target.has("itf.capabilities.platform.instance"):
        session.check("platform.running", target.platform.running())


@hookimpl
def itf_teardown(session):
    """Evidence, collected while the target still runs: console transcript and container output."""
    target = session.target
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    if target.has(CONSOLE):
        path = EVIDENCE / "console.txt"
        path.write_text("\n".join(target.console.lines()), encoding="utf-8")
        log.info("teardown: console transcript (%d lines) saved to %s", len(target.console.lines()), path)
    container = (
        getattr(target.platform, "container", None) if target.has("itf.capabilities.platform.instance") else None
    )
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
    def spawn(self, binary_path: str, args: list[str] | None = None, cwd: str = "/"): ...


# Planned only when a recipe needs the state (the DLT recipes relate logs.active to it).
@delivers(
    "bench.dlt_daemon.running",
    name="bench.start_dlt_daemon",
    requires=("itf.states.platform.up",),
    uses={"process": "itf.capabilities.exec.process"},
)
def start_dlt_daemon(process: Process):
    _daemon["handle"] = process.spawn("/usr/bin/dlt-daemon")


@start_dlt_daemon.probe
def dlt_daemon_running(process: Process):
    return "handle" in _daemon and _daemon["handle"].is_running()
