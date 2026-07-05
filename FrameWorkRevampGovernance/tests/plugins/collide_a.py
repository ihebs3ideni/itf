"""One of two plugins that both contribute to the UNIQUE ctf_provision point."""

from __future__ import annotations


def provision_a(ctx):
    return "a"


def pytest_ctf_steps(steps, config):
    steps.add("ctf_provision", provision_a, name="provision_a")
