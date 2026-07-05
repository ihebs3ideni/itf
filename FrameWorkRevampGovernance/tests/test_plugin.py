from __future__ import annotations

_BAD_CONFTEST = """
from ctf.contracts import provides

@provides("client")          # unprefixed -> violates namespace policy
def client():
    return object()

def pytest_ctf_setup(registry, config):
    registry.register(client)
"""


def test_strict_mode_blocks_unnamespaced_contract(pytester):
    pytester.makeini("[pytest]\nctf_governance = strict\n")
    pytester.makeconftest(_BAD_CONFTEST)
    pytester.makepyfile("def test_x():\n    assert True\n")
    result = pytester.runpytest_subprocess()
    # GovernanceViolation is a CompositionError, so CTF's error boundary turns
    # it into a clean stop (no INTERNALERROR).
    assert result.ret != 0
    result.stderr.fnmatch_lines(
        [
            "ERROR: CTF could not assemble the test environment*",
            "*GovernanceViolation: CTF governance*namespace policy*",
            "*'client'*3 '/'-separated segments*",
        ]
    )


def test_warn_mode_allows_run(pytester):
    pytester.makeini("[pytest]\nctf_governance = warn\n")
    pytester.makeconftest(_BAD_CONFTEST)
    pytester.makepyfile("def test_x():\n    assert True\n")
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(passed=1)


def test_off_mode_is_silent(pytester):
    pytester.makeini("[pytest]\nctf_governance = off\n")
    pytester.makeconftest(_BAD_CONFTEST)
    pytester.makepyfile("def test_x():\n    assert True\n")
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(passed=1)
    assert "namespace policy" not in "\n".join(result.stdout.lines)
