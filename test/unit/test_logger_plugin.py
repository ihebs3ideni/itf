"""Smoke test for the ITF logger plugin — verifies all sections are emitted."""

import textwrap
from pathlib import Path

pytest_plugins = ["pytester"]


def test_logger_emits_all_sections(pytester, tmp_path):
    """Full lifecycle with logger produces section-separated log file."""
    logfile = tmp_path / "test.log"

    pytester.makeconftest(
        textwrap.dedent(f"""\
            import pytest
            from score.itf.core.ctf.contracts import provides, requires
            from score.itf.core.ctf.target import TARGET_ANCHOR

            pytest_plugins = [
                "score.itf.core.itf_plugin",
                "score.itf.plugins.utility.logger.plugin",
            ]

            @pytest.hookimpl
            def pytest_itf_declare(registry, config):
                from score.itf.core.ctf.descriptor import Descriptor
                registry.add_descriptor(Descriptor("itf/target/mock/image", "test:latest"))

                @provides(TARGET_ANCHOR)
                @requires("itf/target/mock/image")
                def mock_target(image):
                    return {{"name": "mock", "image": image}}
                registry.register(mock_target)

                @provides("itf/cap/exec")
                @requires(TARGET_ANCHOR)
                def mock_exec(target):
                    return {{"execute": lambda cmd: (0, "ok")}}
                registry.register(mock_exec)

                @provides("itf/net/ip_address")
                @requires(TARGET_ANCHOR)
                def mock_ip(target):
                    return "192.168.1.100"
                registry.register(mock_ip)

            @pytest.hookimpl
            def pytest_itf_aliases(dut, config):
                dut.alias("shell", "itf/cap/exec")
                dut.alias("target", "ctf/target")

            @pytest.hookimpl
            def pytest_itf_verify(dut, config):
                target = dut.require("ctf/target")
                assert target["name"] == "mock"
        """)
    )
    pytester.makepyfile(
        textwrap.dedent("""\
            def test_cap_available(dut):
                shell = dut.require("itf/cap/exec")
                assert shell is not None

            def test_alias_works(dut):
                shell = dut["shell"]
                assert shell is not None
        """)
    )
    result = pytester.runpytest(f"--itf-logfile={logfile}", "-v")
    result.assert_outcomes(passed=2)

    log_content = logfile.read_text()

    # Verify all expected sections are present
    assert "SESSION START" in log_content
    assert "DECLARE" in log_content
    assert "COMPOSITION GRAPH" in log_content
    assert "ALIASES" in log_content
    assert "VERIFY" in log_content
    assert "TEST SETUP" in log_content
    assert "TEST CALL" in log_content
    assert "TEST TEARDOWN" in log_content
    assert "SESSION FINISH" in log_content

    # Verify graph content
    assert "Tier 0" in log_content
    assert "Tier 1" in log_content
    assert "itf/target/mock/image" in log_content
    assert "ctf/target" in log_content
    assert "itf/cap/exec" in log_content

    # Verify aliases logged
    assert "shell -> itf/cap/exec" in log_content
    assert "target -> ctf/target" in log_content

    # Verify format matches [timestamp] [LVL] [source] pattern
    import re

    pattern = r"\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}\] \[\w{3}\] \[\w+"
    assert re.search(pattern, log_content)
