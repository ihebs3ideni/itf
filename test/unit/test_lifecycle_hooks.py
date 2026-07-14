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
"""Tests validating the ITF phased lifecycle hookspec system.

Uses pytester to spin up a real pytest session with the mock target
and verifies that hooks fire in the correct order.
"""

import textwrap

pytest_plugins = ["pytester"]


def test_lifecycle_hooks_fire_in_order(pytester):
    """All lifecycle hooks fire in the correct session/test order."""
    pytester.makeconftest(
        textwrap.dedent("""\
            import pytest
            from score.itf.core.ctf.contracts import provides
            from score.itf.core.ctf.target import TARGET_ANCHOR

            pytest_plugins = ["score.itf.core.itf_plugin"]

            CALL_LOG = []

            @pytest.hookimpl
            def pytest_itf_declare(registry, config):
                @provides(TARGET_ANCHOR)
                def test_anchor():
                    return {"name": "lifecycle_test_target"}

                registry.register(test_anchor)

            @pytest.hookimpl
            def pytest_itf_init(dut, config):
                CALL_LOG.append("init")

            @pytest.hookimpl
            def pytest_itf_provision(dut, config):
                CALL_LOG.append("provision")

            @pytest.hookimpl
            def pytest_itf_verify(dut, config):
                CALL_LOG.append("verify")

            @pytest.hookimpl
            def pytest_itf_teardown(dut, config):
                CALL_LOG.append("teardown")

            @pytest.fixture
            def call_log():
                return CALL_LOG
        """)
    )
    pytester.makepyfile(
        textwrap.dedent("""\
            def test_one(call_log):
                assert "init" in call_log
                assert "provision" in call_log
                assert "verify" in call_log

            def test_two(call_log):
                # Session hooks already fired before any test
                assert call_log == ["init", "provision", "verify"]
        """)
    )
    result = pytester.runpytest("-v")
    result.assert_outcomes(passed=2)


def test_verify_hook_receives_dut(pytester):
    """The verify hook receives a functional DUT with resolved contracts."""
    pytester.makeconftest(
        textwrap.dedent("""\
            import pytest
            from score.itf.core.ctf.contracts import provides, requires
            from score.itf.core.ctf.target import TARGET_ANCHOR

            pytest_plugins = ["score.itf.core.itf_plugin"]

            @pytest.hookimpl
            def pytest_itf_declare(registry, config):
                @provides(TARGET_ANCHOR)
                def test_anchor():
                    return {"type": "mock"}

                @provides("itf/net/ip_address")
                @requires(TARGET_ANCHOR)
                def ip_address(target):
                    return "192.168.1.1"

                registry.register(test_anchor)
                registry.register(ip_address)

            @pytest.hookimpl
            def pytest_itf_verify(dut, config):
                # DUT should be fully resolved by the time verify fires
                assert dut.available("itf/net/ip_address")
                ip = dut.require("itf/net/ip_address")
                assert ip == "192.168.1.1"
        """)
    )
    pytester.makepyfile(
        textwrap.dedent("""\
            def test_passes(dut):
                assert dut.require("itf/net/ip_address") == "192.168.1.1"
        """)
    )
    result = pytester.runpytest("-v")
    result.assert_outcomes(passed=1)


def test_verify_failure_aborts_session(pytester):
    """If a verify hook raises, the session is aborted cleanly."""
    pytester.makeconftest(
        textwrap.dedent("""\
            import pytest
            from score.itf.core.ctf.contracts import provides
            from score.itf.core.ctf.target import TARGET_ANCHOR

            pytest_plugins = ["score.itf.core.itf_plugin"]

            @pytest.hookimpl
            def pytest_itf_declare(registry, config):
                @provides(TARGET_ANCHOR)
                def test_anchor():
                    return {"type": "mock"}

                registry.register(test_anchor)

            @pytest.hookimpl
            def pytest_itf_verify(dut, config):
                raise AssertionError("Target not reachable!")
        """)
    )
    pytester.makepyfile(
        textwrap.dedent("""\
            def test_should_not_run():
                assert False, "This test should never execute"
        """)
    )
    result = pytester.runpytest("-v")
    # UsageError aborts the session — no tests run, exit code != 0
    assert result.ret != 0
    # The error message appears in stdout or stderr
    output = str(result.stdout) + str(result.stderr)
    assert "Target not reachable" in output


def test_multiple_plugins_verify_hooks(pytester):
    """Multiple plugins can contribute to the same lifecycle hook."""
    pytester.makeconftest(
        textwrap.dedent("""\
            import pytest
            from score.itf.core.ctf.contracts import provides, requires
            from score.itf.core.ctf.target import TARGET_ANCHOR

            pytest_plugins = ["score.itf.core.itf_plugin"]

            CHECKS = []

            @pytest.hookimpl
            def pytest_itf_declare(registry, config):
                @provides(TARGET_ANCHOR)
                def test_anchor():
                    return {"type": "mock"}

                @provides("itf/cap/exec")
                @requires(TARGET_ANCHOR)
                def mock_exec(target):
                    return target

                registry.register(test_anchor)
                registry.register(mock_exec)

            @pytest.hookimpl
            def pytest_itf_verify(dut, config):
                # First plugin checks target
                CHECKS.append("target_check")

            @pytest.fixture
            def checks():
                return CHECKS
        """)
    )
    pytester.makepyfile(
        conftest_extra=textwrap.dedent("""\
            # This simulates a second plugin contributing a verify hook
        """),
    )
    pytester.makepyfile(
        textwrap.dedent("""\
            def test_both_checks_ran(checks):
                assert "target_check" in checks
        """)
    )
    result = pytester.runpytest("-v")
    result.assert_outcomes(passed=1)


def test_plugin_verify_failure_in_loose_mode_warns(pytester):
    """Plugin verify failure in LOOSE mode logs warning, does not abort."""
    # Create a fake plugin module (not a conftest) with a failing verify hook
    pytester.makepyfile(
        my_plugin=textwrap.dedent("""\
            import pytest

            @pytest.hookimpl
            def pytest_itf_verify(dut, config):
                raise AssertionError("Plugin check failed!")
        """)
    )
    pytester.makeconftest(
        textwrap.dedent("""\
            import pytest
            from score.itf.core.ctf.contracts import provides
            from score.itf.core.ctf.target import TARGET_ANCHOR

            pytest_plugins = ["score.itf.core.itf_plugin", "my_plugin"]

            @pytest.hookimpl
            def pytest_itf_declare(registry, config):
                @provides(TARGET_ANCHOR)
                def test_anchor():
                    return {"type": "mock"}

                registry.register(test_anchor)
        """)
    )
    pytester.makepyfile(
        textwrap.dedent("""\
            def test_still_runs(dut):
                # This test should run because the plugin failure is non-fatal
                assert dut.require("ctf/target") == {"type": "mock"}
        """)
    )
    # Default mode is LOOSE — plugin failure should warn, not abort
    result = pytester.runpytest("-v", "--log-cli-level=WARNING")
    result.assert_outcomes(passed=1)
    result.stdout.fnmatch_lines(["*Plugin check failed*"])


def test_conftest_verify_failure_always_aborts(pytester):
    """Conftest verify failure always aborts, even in LOOSE mode."""
    pytester.makeconftest(
        textwrap.dedent("""\
            import pytest
            from score.itf.core.ctf.contracts import provides
            from score.itf.core.ctf.target import TARGET_ANCHOR

            pytest_plugins = ["score.itf.core.itf_plugin"]

            @pytest.hookimpl
            def pytest_itf_declare(registry, config):
                @provides(TARGET_ANCHOR)
                def test_anchor():
                    return {"type": "mock"}

                registry.register(test_anchor)

            @pytest.hookimpl
            def pytest_itf_verify(dut, config):
                raise AssertionError("Conftest health check failed!")
        """)
    )
    pytester.makepyfile(
        textwrap.dedent("""\
            def test_should_not_run():
                assert False, "Should never execute"
        """)
    )
    result = pytester.runpytest("-v")
    assert result.ret != 0
    output = str(result.stdout) + str(result.stderr)
    assert "Conftest health check failed" in output
