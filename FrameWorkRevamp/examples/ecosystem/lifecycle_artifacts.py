"""LIFECYCLE plugin: provisioning + per-test artifact collection.

Demonstrates the phase plane. It contributes *steps* to extension points; the
engine schedules them by riding pytest's own hooks. This plugin knows nothing
about DoIP/UDS -- it only pulls resources from the DUT by contract when its
steps run.

* ``ctf_provision`` (FANOUT)  -- one or more provisioners run at session start;
  each only pulls resources from the DUT by contract.
* ``ctf_after_test`` (FANOUT) -- collect a log artifact after every test.
* ``ctf_session_teardown``    -- final report of everything collected.
"""

from __future__ import annotations


def provision(ctx):
    # Session bring-up: prove the SSH endpoint fact is reachable, once.
    host = ctx.require("endpoint/ssh")
    ctx.artifacts.add("provisioned", host)


def collect_after_test(ctx):
    node = ctx.item.nodeid if ctx.item is not None else "<unknown>"
    outcome = getattr(ctx.report, "outcome", "n/a")
    ctx.artifacts.add(f"log:{node}", outcome)


def final_report(ctx):
    ctx.artifacts.add("report", f"{len(ctx.artifacts.items)} artifacts")


def pytest_ctf_steps(steps, config):
    steps.add("ctf_provision", provision)
    steps.add("ctf_after_test", collect_after_test)
    steps.add("ctf_session_teardown", final_report)
