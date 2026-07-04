"""Example tests for ITF v2 framework."""

import pytest


def test_target_exists(context=None):
    """Verify target is available."""
    # In a real test, context would be injected via fixture
    assert True, "Target should exist"


def test_ssh_capability():
    """Verify SSH capability is available."""
    # In real tests, would verify ssh executor exists and works
    assert True, "SSH capability should be available"


def test_exec_command():
    """Test command execution via mock SSH."""
    # In a real test:
    # result = context.shared_resources["ssh_executor"].run_command("whoami")
    # assert result[0] == 0, f"Command failed: {result[2]}"
    assert True, "Command should execute"


def test_log_output(capsys):
    """Test that output is captured in logs."""
    print("Test output message")
    captured = capsys.readouterr()
    assert "Test output message" in captured.out


@pytest.mark.skip(reason="example skip")
def test_skipped():
    """Example skipped test."""
    pass
