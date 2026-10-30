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
"""Map pytest discovery and lifecycle onto an ITF session.

Run logging is a companion plugin; this module owns resolution, gating, bring-up and unwind.
"""

from __future__ import annotations

import logging
import os
import shutil
import warnings
from pathlib import Path
from types import ModuleType

import pluggy
import pytest

from ... import gating as itf_gating
from ...engine.contexts import WrongPhase
from ...engine.failure import banner
from ...engine.hooks import HOOK_NAMES, ITFHookSpecs, implements_itf_hooks
from ...engine.registry import CrossContributorImport, is_contributor
from ...session import (
    ConfigValidationFailed,
    DescribeResult,
    NotReady,
    ResolutionFailed,
    Session,
    TargetNameClash,
)

pytest_plugins = ["score.itf.core.adapters.pytest.run_logging"]
_pytest_hookspec = pluggy.HookspecMarker("pytest")
logger = logging.getLogger(__name__)


class _AdapterHookSpecs:
    @_pytest_hookspec
    def pytest_itf_session_created(self, config, session, contributors):
        """An ITF session exists but has not resolved or accessed its target yet."""


def pytest_addhooks(pluginmanager):
    """Declare the itf_* hooks to pytest too, so `@pytest.hookimpl` on them is accepted."""
    for name in HOOK_NAMES:
        _pytest_hookspec(getattr(ITFHookSpecs, name))
    pluginmanager.add_hookspecs(ITFHookSpecs)
    pluginmanager.add_hookspecs(_AdapterHookSpecs)


def pytest_addoption(parser):
    group = parser.getgroup("itf")
    group.addoption(
        "--itf-plan",
        action="store_true",
        default=False,
        dest="itf_plan",
        help="resolve and print the plan and gating; run nothing",
    )
    group.addoption(
        "--itf-fresh",
        action="store_true",
        default=False,
        dest="itf_fresh",
        help="reuse=fresh: run every planned action, ignoring what probes observe",
    )
    group.addoption(
        "--itf-keep",
        action="store_true",
        default=False,
        dest="itf_keep",
        help="on_exit=keep: run teardown hooks, skip unwind",
    )
    group.addoption(
        "--itf-strict-gating",
        action="store_true",
        default=False,
        dest="itf_strict_gating",
        help="a deselection becomes a failure",
    )
    group.addoption(
        "--itf-strict-shapes",
        action="store_true",
        default=False,
        dest="itf_strict_shapes",
        help="an undeclared shape expectation is an error",
    )
    group.addoption(
        "--itf-run-dir",
        action="store",
        default=None,
        dest="itf_run_dir",
        help="where run artifacts and logs go (default: $TEST_UNDECLARED_OUTPUTS_DIR/itf-run "
        "under Bazel, else itf-run/ in the pytest root directory)",
    )
    group.addoption(
        "--itf-config",
        action="store",
        default=None,
        dest="itf_config",
        help="path to a YAML config (or inline YAML/JSON text); also settable via the ITF_CONFIG env var",
    )


def _conftest_dir(module: ModuleType) -> Path | None:
    file = getattr(module, "__file__", None)
    return Path(file).resolve().parent if file and Path(file).name == "conftest.py" else None


def contributors_from_pytest(pluginmanager) -> list[tuple[ModuleType, str]]:
    """The root conftest ranks as `conftest`; every other ITF-capable plugin as `plugin`."""
    modules = [p for p in pluginmanager.get_plugins() if isinstance(p, ModuleType)]
    conftest_dirs = [d for d in map(_conftest_dir, modules) if d is not None]
    root = min(conftest_dirs, key=lambda d: len(d.parts), default=None)
    entries = []
    for module in modules:
        where = _conftest_dir(module)
        if where is not None:
            if where == root:
                entries.append((module, "conftest"))
            elif implements_itf_hooks(module):
                warnings.warn(f"itf: ignoring ITF hooks in {module.__file__}; only the root conftest is a recipe")
        elif is_contributor(module):
            entries.append((module, "plugin"))
    return entries


def _run_dir(config) -> Path:
    explicit = config.getoption("itf_run_dir")
    if explicit:
        return Path(explicit)
    bazel_outputs = os.environ.get("TEST_UNDECLARED_OUTPUTS_DIR")
    if bazel_outputs:
        return Path(bazel_outputs) / "itf-run"
    return Path(str(config.rootpath)) / "itf-run"


@pytest.hookimpl(trylast=True)
def pytest_configure(config):
    config._itf_session = None

    # --itf-config pre-fills the same environment variable that recipes already read.
    cli_config = config.getoption("itf_config")
    if cli_config:
        os.environ["ITF_CONFIG"] = cli_config

    contributors = contributors_from_pytest(config.pluginmanager)
    if not any(implements_itf_hooks(module) for module, _ in contributors):
        return

    run_dir = _run_dir(config)
    session = Session(
        contributors=contributors,
        plan_only=bool(config.getoption("itf_plan")),
        gating="fail" if config.getoption("itf_strict_gating") else "skip",
        reuse="fresh" if config.getoption("itf_fresh") else "probe",
        on_exit="keep" if config.getoption("itf_keep") else "unwind",
        strict_shapes=bool(config.getoption("itf_strict_shapes")),
        run_dir=run_dir,
    )
    config._itf_session = session
    config.hook.pytest_itf_session_created(config=config, session=session, contributors=contributors)
    try:
        session.resolve()
    except ResolutionFailed as exc:
        raise pytest.UsageError(_section(f"ITF: plan failed at gate {exc.gate}", exc.rendered)) from exc
    except (ConfigValidationFailed, TargetNameClash) as exc:
        logger.error("itf: %s", exc)
        raise pytest.UsageError(_section("ITF: recipe rejected", str(exc))) from exc
    except (CrossContributorImport, WrongPhase, TypeError, ValueError) as exc:
        logger.error("itf: %s: %s", type(exc).__name__, exc)
        raise pytest.UsageError(_section("ITF: recipe rejected", f"{type(exc).__name__}: {exc}")) from exc


def _section(title: str, body: str) -> str:
    """A pytest-style `=== title ===` block, for errors raised before the terminal reporter is writing."""
    width = shutil.get_terminal_size((100, 20)).columns
    return f"\n{banner(title, width)}\n{body}\n{'=' * width}"


def _show(config, failure) -> None:
    """Print a failure report as its own section, the way pytest prints `=== FAILURES ===`."""
    text = failure.render()
    reporter = config.pluginmanager.get_plugin("terminalreporter")
    if reporter is None:
        print(text)
        return
    reporter.write_line("")
    for line in text.splitlines():
        reporter.write_line(line, red=line.startswith("="), bold=line.startswith("="))


def pytest_collection_modifyitems(config, items):
    session = getattr(config, "_itf_session", None)
    if session is None:
        return

    requirements = {}
    for item in items:
        fn = getattr(item, "obj", None)
        requirements[item.nodeid] = itf_gating.get_requirements(fn) if fn is not None else ()
    decisions = session.select(requirements)

    if session.gating == "fail":
        session._gating_lookup = decisions
    else:
        remaining = []
        deselected = []
        for item in items:
            decision = decisions.get(item.nodeid)
            if decision is not None and not decision.selected:
                deselected.append(item)
            else:
                remaining.append(item)
        if deselected:
            items[:] = remaining
            config.hook.pytest_deselected(items=deselected)

    if config.getoption("itf_plan"):
        print(DescribeResult(session).render())
        print("Gating:")
        for test_id, decision in session._gating_decisions:
            state = "selected" if decision.selected else f"deselected: {decision.reason}"
            print(f"  {test_id}: {state}")
        pytest.exit("itf: --itf-plan, nothing run", returncode=0)


def pytest_runtest_setup(item):
    session = getattr(item.config, "_itf_session", None)
    if session is None or session.gating != "fail":
        return
    decision = getattr(session, "_gating_lookup", {}).get(item.nodeid)
    if decision is not None and not decision.selected:
        pytest.fail(f"itf gating (strict): {decision.reason}", pytrace=False)


def _itf_session_of(request):
    session = getattr(request.config, "_itf_session", None)
    if session is None:
        pytest.fail(
            "itf: no recipe: the root conftest implements no itf_setup/itf_init hook, so there is no target",
            pytrace=False,
        )
    return session


@pytest.fixture(scope="session")
def target(request):
    return _itf_session_of(request).target


@pytest.fixture(scope="session")
def session(request):
    return request.config._itf_session


def pytest_collection_finish(session):
    """Bring-up happens after collection/gating and before the test loop."""
    config = session.config
    itf_session = getattr(config, "_itf_session", None)
    if itf_session is None or itf_session.plan_only or config.option.collectonly:
        return
    if not session.items:
        return
    config._itf_brought_up = True
    try:
        itf_session.bring_up()
    except NotReady as exc:
        if exc.failure is not None:
            _show(config, exc.failure)
        itf_session.close()
        _show_close_problems(config, itf_session)
        pytest.exit(f"itf: session not ready: {exc}", returncode=1)


def _show_close_problems(config, itf_session) -> None:
    # pytest_sessionfinish runs again after pytest.exit: report the closing problems once.
    problems = None if getattr(config, "_itf_close_shown", False) else itf_session.close_problems()
    config._itf_close_shown = True
    if problems is not None:
        _show(config, problems)


def pytest_sessionfinish(session):
    config = session.config
    itf_session = getattr(config, "_itf_session", None)
    if itf_session is not None and getattr(config, "_itf_brought_up", False):
        itf_session.close()
        _show_close_problems(config, itf_session)
