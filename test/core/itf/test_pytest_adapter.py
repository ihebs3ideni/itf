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
"""The pytest adapter (docs/octo-kit/12-spec-itf-core.md §7)."""

from __future__ import annotations

import io
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _setup(pytester):
    pytester.syspathinsert(str(FIXTURES_DIR))


def _run(pytester, *args):
    # The adapter arrives through itf-core's pytest11 entry point, as it does for users.
    return pytester.runpytest(*args)


def _root_conftest_is(pytester, recipe: str) -> None:
    """The recipe fixture becomes the root conftest itself, which is how a project uses ITF."""
    pytester.makeconftest((FIXTURES_DIR / f"{recipe}.py").read_text())


def test_adapter_is_inert_without_itf_hooks(pytester):
    _setup(pytester)
    pytester.makepyfile("def test_ok():\n    assert True\n")
    result = _run(pytester)
    result.assert_outcomes(passed=1)
    assert not (pytester.path / "itf-run" / "test.log").exists()
    assert not (pytester.path / "itf-run" / "events.jsonl").exists()


def test_adapter_runs_without_the_logging_plugin(pytester):
    _setup(pytester)
    pytester.makepyfile("def test_ok(target):\n    assert target.main.shell.run('echo ok')\n")
    _root_conftest_is(pytester, "shell_recipe")
    result = _run(pytester, "-p", "no:score.itf.core.adapters.pytest.run_logging")
    result.assert_outcomes(passed=1)
    run_dir = pytester.path / "itf-run"
    assert (run_dir / "plan.json").exists()
    assert not (run_dir / "test.log").exists()
    assert not (run_dir / "events.jsonl").exists()
    assert "ITF session" not in result.stdout.str()


def test_adapter_full_lifecycle_with_target_fixture(pytester):
    _setup(pytester)
    pytester.makepyfile("""
        import score.itf.core as itf

        @itf.requires("itf.capabilities.exec.shell", scope="main")
        def test_uses_shell(target):
            assert target.main.has("itf.capabilities.exec.shell")
            assert "shell" in target.main.names()
    """)
    _root_conftest_is(pytester, "shell_recipe")
    result = _run(pytester, "-v")
    result.assert_outcomes(passed=1)
    result.stdout.fnmatch_lines(["*test_uses_shell*PASSED*"])


def test_adapter_writes_run_log_with_itf_pack_and_test_records(pytester):
    _setup(pytester)
    pytester.makepyfile("""
        import logging

        def test_logs(target):
            logging.getLogger("bench.test").info("from the test")
    """)
    _root_conftest_is(pytester, "shell_recipe")
    _run(pytester).assert_outcomes(passed=1)
    log = (pytester.path / "itf-run" / "test.log").read_text()
    for expected in (
        "score.itf.core: ============ itf: resolve",
        "itf: bring-up",
        "from the test",
        "itf: close",
        "unwind:",
    ):
        assert expected in log
    assert logging.getLogger().handlers == [
        h for h in logging.getLogger().handlers if not str(getattr(h, "baseFilename", "")).endswith("test.log")
    ]


def test_adapter_run_log_mirrors_the_pytest_session(pytester):
    _setup(pytester)
    (pytester.path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    pytester.makepyfile("""
        import warnings
        import pytest

        def test_passes(target):
            print("hello stdout")

        def test_fails(target):
            assert 1 == 2, "boom"

        def test_skips(target):
            pytest.skip("not today")

        def test_warns(target):
            warnings.warn("careful")
    """)
    _root_conftest_is(pytester, "shell_recipe")
    _run(pytester, "-v", "--color=yes").assert_outcomes(passed=2, failed=1, skipped=1)
    log = (pytester.path / "itf-run" / "test.log").read_text(encoding="utf-8")
    for expected in (
        "itf.pytest: pytest ",
        "invocation: pytest",
        "collected 4 item(s):",
        "START test_adapter_run_log_mirrors_the_pytest_session.py::test_passes",
        "PASSED test_adapter_run_log_mirrors_the_pytest_session.py::test_passes (call",
        "Captured stdout call",
        "hello stdout",
        "FAILED test_adapter_run_log_mirrors_the_pytest_session.py::test_fails (call",
        "AssertionError: boom",
        "SKIPPED",
        "not today",
        "UserWarning: careful",
        "session finished: exit status 1 (1 failed, 2 passed, 1 skipped",
    ):
        assert expected in log, expected
    for expected in (
        "test session starts",
        "platform ",
        "Python ",
        "pytest-",
        "pluggy-",
        "rootdir:",
        "configfile: pytest.ini",
        "short test summary info",
        "1 failed, 2 passed, 1 skipped",
        " in ",
    ):
        assert expected in log, expected
    assert "\x1b[" not in log


def test_adapter_emits_itf_header_with_versions_and_loaded_plugins(pytester):
    _setup(pytester)
    pytester.makepyfile("def test_ok(target):\n    pass\n")
    _root_conftest_is(pytester, "shell_recipe")
    result = _run(pytester, "--itf-plan", "--itf-fresh")
    assert result.ret == 0
    log = (pytester.path / "itf-run" / "test.log").read_text(encoding="utf-8")
    for expected in (
        "ITF session",
        "core: ",
        "runtime: Python ",
        "pluggy ",
        "adapter: score.itf.core.adapters.pytest.plugin",
        "mode: plan-only, reuse=fresh",
        "strict_shapes=False",
        "artifacts:",
        "recipe:",
        "fake_shell.plugin",
        "plugins (pack / version / entrypoints):",
    ):
        assert expected in log, expected
        assert expected in result.stdout.str(), expected
    events = [
        json.loads(line)
        for line in (pytester.path / "itf-run" / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    plugins = [event["message"] for event in events if event["message"].startswith("  fake_shell /")]
    assert plugins == ["  fake_shell / source / fake_shell.plugin"]
    assert "contributors:" not in log and "loaded plugin modules:" not in log
    assert "Gating:" not in log


def test_adapter_log_is_line_oriented_and_structured_without_live_duplicates(pytester):
    _setup(pytester)
    (pytester.path / "pytest.ini").write_text("[pytest]\nlog_cli = true\nlog_cli_level = INFO\n", encoding="utf-8")
    pytester.makepyfile("""
        import logging

        def test_events(target):
            logging.getLogger("bench.test").info("first line\\nsecond line")
    """)
    _root_conftest_is(pytester, "shell_recipe")
    result = _run(pytester, "-v", "--color=yes")
    result.assert_outcomes(passed=1)
    assert "first line" in result.stdout.str()
    run_dir = pytester.path / "itf-run"
    text = (run_dir / "test.log").read_text(encoding="utf-8")
    events = [json.loads(line) for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert all(
        re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}\+00:00 [A-Z]+\s+\S+: ", line)
        for line in text.splitlines()
    )
    assert "collecting ... 20" not in text
    assert "\x1b[" not in text
    assert text.count("first line") == 1
    assert text.count("second line") == 1
    assert [event["sequence"] for event in events] == list(range(1, len(events) + 1))
    assert all(event["schema_version"] == 1 for event in events)
    assert all(event["timestamp"].endswith("+00:00") for event in events)
    assert [event["message"] for event in events if event["logger"] == "bench.test"] == ["first line\nsecond line"]
    assert not any("first line" in event["message"] for event in events if event["logger"] == "pytest.terminal")
    reports = [event["event"] for event in events if event.get("event", {}).get("kind") == "test_report"]
    assert reports[0]["outcome"] == "passed"
    assert reports[0]["phase"] == "call"
    assert reports[0]["duration"] >= 0
    assert reports[0]["nodeid"].endswith("::test_events")


def test_run_log_flushes_partial_terminal_lines_before_records_and_on_close(tmp_path):
    from score.itf.core.adapters.pytest.run_logging import _ReporterStream, _RunLogHandler

    terminal = io.StringIO()
    handler = _RunLogHandler(tmp_path)
    stream = _ReporterStream(terminal, handler)
    handler.reporter = stream
    try:
        stream.write("collecting ... ")
        handler.handle(logging.LogRecord("example", logging.INFO, "", 0, "during collection", (), None))
        stream.write("summary without a newline")
    finally:
        handler.close()
    events = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [(event["logger"], event["message"]) for event in events] == [
        ("pytest.terminal", "collecting ..."),
        ("example", "during collection"),
        ("pytest.terminal", "summary without a newline"),
    ]
    assert terminal.getvalue() == "collecting ... summary without a newline"


def test_run_log_preserves_exception_details_in_structured_event(tmp_path):
    from score.itf.core.adapters.pytest.run_logging import _RunLogHandler

    handler = _RunLogHandler(tmp_path)
    try:
        try:
            raise ValueError("invalid input")
        except ValueError:
            import sys

            handler.handle(logging.LogRecord("example", logging.ERROR, "", 0, "operation failed", (), sys.exc_info()))
    finally:
        handler.close()
    events = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(events) == 1
    assert events[0]["level"] == "ERROR"
    assert "ValueError: invalid input" in events[0]["exception"]
    assert "ERROR   example: ValueError: invalid input" in (tmp_path / "test.log").read_text(encoding="utf-8")


def test_run_log_serializes_concurrent_writers(tmp_path):
    from score.itf.core.adapters.pytest.run_logging import _RunLogHandler

    handler = _RunLogHandler(tmp_path)

    def write(index):
        handler.handle(logging.LogRecord("worker", logging.DEBUG, "", 0, "sample %s", (index,), None))

    try:
        with ThreadPoolExecutor(max_workers=4) as workers:
            list(workers.map(write, range(100)))
    finally:
        handler.close()
    events = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [event["sequence"] for event in events] == list(range(1, 101))
    assert {event["message"] for event in events} == {f"sample {index}" for index in range(100)}
    assert all(event["level"] == "DEBUG" for event in events)
    assert all(
        {"schema_version", "sequence", "timestamp", "level", "logger", "message"} <= event.keys() for event in events
    )


def test_adapter_header_without_terminal_reporter(pytester):
    _setup(pytester)
    pytester.makepyfile("def test_ok(target):\n    pass\n")
    _root_conftest_is(pytester, "shell_recipe")
    result = _run(pytester, "-p", "no:terminal")
    assert result.ret == 0
    log = (pytester.path / "itf-run" / "test.log").read_text(encoding="utf-8")
    assert "itf.pytest: ITF session" in log
    assert "mode: execute" in log
    assert "core: " in log


def test_adapter_run_log_level_option_and_plan_only(pytester):
    _setup(pytester)
    pytester.makepyfile("def test_ok(target):\n    pass\n")
    _root_conftest_is(pytester, "shell_recipe")
    _run(pytester, "--itf-plan", "--itf-log-level", "warning")
    assert "itf: resolve" not in (pytester.path / "itf-run" / "test.log").read_text()
    events = [
        json.loads(line)
        for line in (pytester.path / "itf-run" / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert not any(event["logger"] == "score.itf.core" and event["level"] in ("DEBUG", "INFO") for event in events)
    assert any(event["logger"] == "pytest.terminal" for event in events)
    result = _run(pytester, "--itf-plan")
    log = (pytester.path / "itf-run" / "test.log").read_text()
    assert "Gate 1 (itf_setup): resolved" in log
    # The plan is an artifact (stdout, plan.json, target.html), not a log record.
    result.stdout.fnmatch_lines(["Gating:"])
    assert (pytester.path / "itf-run" / "plan.json").is_file()
    assert "Gating:" not in log and "Construction order" not in log


def test_adapter_gating_deselects_by_default(pytester):
    _setup(pytester)
    pytester.makepyfile("""
        import score.itf.core as itf

        @itf.requires("itf.capabilities.exec.shell", scope="main")
        def test_needs_shell(target):
            assert target.main.has("itf.capabilities.exec.shell")

        @itf.requires("nonexistent.token", scope="main")
        def test_needs_missing(target):
            assert False
    """)
    _root_conftest_is(pytester, "shell_recipe")
    result = _run(pytester, "-v")
    result.assert_outcomes(passed=1, deselected=1)


def test_adapter_strict_gating_fails_instead_of_skipping(pytester):
    _setup(pytester)
    pytester.makepyfile("""
        import score.itf.core as itf

        @itf.requires("itf.capabilities.exec.shell", scope="main")
        def test_needs_shell(target):
            assert target.main.has("itf.capabilities.exec.shell")

        @itf.requires("nonexistent.token", scope="main")
        def test_needs_missing(target):
            assert False
    """)
    _root_conftest_is(pytester, "shell_recipe")
    result = _run(pytester, "--itf-strict-gating", "-v")
    # a strict-gating rejection surfaces as a setup-phase error, which pytest
    # categorizes separately from a call-phase failure but still fails the run.
    result.assert_outcomes(passed=1, errors=1)


def test_adapter_plan_mode_runs_nothing(pytester):
    _setup(pytester)
    pytester.makepyfile("""
        import score.itf.core as itf

        @itf.requires("itf.capabilities.exec.shell", scope="main")
        def test_uses_shell(target):
            assert target.main.has("itf.capabilities.exec.shell")
    """)
    _root_conftest_is(pytester, "shell_recipe")
    result = _run(pytester, "--itf-plan")
    result.stdout.fnmatch_lines(["*itf: --itf-plan*"])
    result.assert_outcomes()


def test_adapter_resolution_failure_is_a_usage_error(pytester):
    _setup(pytester)
    pytester.makepyfile("def test_never_runs():\n    assert True\n")
    _root_conftest_is(pytester, "broken_recipe")
    result = _run(pytester)
    assert result.ret != 0
    result.stderr.fnmatch_lines(["*Gate 1*itf_setup*"])


def test_adapter_config_failure_is_a_usage_error(pytester):
    _setup(pytester)
    pytester.makeconftest("""
        from score.itf.core import hookimpl
        pytest_plugins = ["config_recipe"]

        @hookimpl
        def itf_setup(ctx):
            ctx.scope("main").add("client", "widget.client", using="fixture.client",
                                  config={"port": "bad"})
    """)
    pytester.makepyfile("def test_never_runs():\n    assert True\n")
    result = _run(pytester, "--itf-plan")
    assert result.ret != 0
    result.stderr.fnmatch_lines(["*main.client*config.host*required str*"])


def test_adapter_shared_recipe_loaded_as_a_plugin(pytester):
    _setup(pytester)
    pytester.makeconftest('pytest_plugins = ["shell_recipe"]\n')
    pytester.makepyfile("""
        import score.itf.core as itf

        @itf.requires("itf.capabilities.exec.shell", scope="main")
        def test_uses_shell(target):
            assert target.main.has("itf.capabilities.exec.shell")
    """)
    result = _run(pytester, "-v")
    result.assert_outcomes(passed=1)


def test_adapter_root_conftest_overrides_a_plugin(pytester):
    _setup(pytester)
    pytester.makeconftest("""
        from score.itf.core import hookimpl

        pytest_plugins = ["shell_recipe"]

        @hookimpl
        def itf_setup(ctx):
            ctx.scope("main").add("shell", "itf.capabilities.exec.shell", using="fake_shell.session",
                                  bind={"world": "world"}, config={"prompt": "root"})
    """)
    pytester.makepyfile("""
        def test_config_came_from_the_root_conftest(session):
            node = [n for n in session.target.main.plan()["target"]["nodes"] if n["name"] == "shell"][0]
            assert node["config"] == {"prompt": "root"}
    """)
    result = _run(pytester, "-v")
    result.assert_outcomes(passed=1)


def test_adapter_reports_a_cross_contributor_import_as_one_usage_error(pytester):
    _setup(pytester)
    pytester.makepyfile("def test_ok():\n    assert True\n")
    _root_conftest_is(pytester, "bad_recipe")
    result = _run(pytester)
    assert result.ret == 4
    result.stderr.fnmatch_lines(["*CrossContributorImport*fake_kv.providers*"])
    assert "INTERNALERROR" not in result.stdout.str() + result.stderr.str()


def test_adapter_writes_artifacts_to_the_bazel_outputs_dir_when_set(pytester, monkeypatch, tmp_path):
    _root_conftest_is(pytester, "shell_recipe")
    monkeypatch.setenv("TEST_UNDECLARED_OUTPUTS_DIR", str(tmp_path / "outputs"))
    assert _run(pytester, "--itf-plan").ret == 0
    assert (tmp_path / "outputs" / "itf-run" / "plan.json").is_file()
    assert not (pytester.path / "itf-run").exists()


def test_adapter_itf_run_dir_option_wins(pytester, monkeypatch, tmp_path):
    _root_conftest_is(pytester, "shell_recipe")
    monkeypatch.setenv("TEST_UNDECLARED_OUTPUTS_DIR", str(tmp_path / "outputs"))
    assert _run(pytester, "--itf-plan", f"--itf-run-dir={tmp_path / 'chosen'}").ret == 0
    assert (tmp_path / "chosen" / "plan.json").is_file()


def test_target_without_a_recipe_fails_with_a_reason(pytester):
    pytester.makepyfile("def test_x(target):\n    pass\n")
    result = _run(pytester)
    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines(["*itf: no recipe*"])
