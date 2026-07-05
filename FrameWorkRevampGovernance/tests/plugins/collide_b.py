"""The second plugin contributing to the UNIQUE ctf_provision point."""

from __future__ import annotations


def provision_b(ctx):
    return "b"


def pytest_ctf_steps(steps, config):
    steps.add("ctf_provision", provision_b, name="provision_b")
