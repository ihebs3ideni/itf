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
"""Demo + CI guard: governance over the *real* CTF scenario contracts.

This binds the governance auditor to the actual capability and scenario
contracts used by the example test levels (``integration``, ``scenario``,
``ssh_demo``). It demonstrates the whole point of the governor:

1. **The defined contract.** The healthy example ecosystem audits *clean* -- the
   public ``ctf/*`` contracts are all present, single-sourced, resolvable and
   well-namespaced. That clean audit *is* the contract baseline.

2. **Nothing may break it.** Any change that violates a contract is caught by the
   same audit -- a duplicate provider, a renamed/typo'd requirement, or a
   mis-namespaced contract. Wire this audit into CI and a contract regression
   fails the build instead of shipping.

Run it as a guard::

    pytest tests/test_scenario_contract_demo.py

or as a printed demo::

    python tests/test_scenario_contract_demo.py
"""

from __future__ import annotations

import pathlib
import sys

import pytest

from ctf.contracts import provides, requires
from ctf_governance.catalog import build_catalog
from ctf_governance.collector import collect, inspect_plugin
from ctf_governance.naming import DEFAULT_POLICY, validate_contract

#: The sibling repo that holds the example plugins under a top-level ``plugins``
#: package. Located relative to this file so the demo is path-independent.
_CTF_EXAMPLES = (
    pathlib.Path(__file__).resolve().parents[2] / "examples" / "examples" / "ctf"
)

#: The public contracts the example levels are written against -- the surface a
#: test author relies on and the governor protects.
_PUBLIC_CONTRACTS = {
    "ctf/host/process",
    "ctf/cap/exec",
    "ctf/cap/file_transfer",
    "ctf/cap/restart",
    "ctf/cap/network",
    "ctf/cap/ping",
    "ctf/scenario/echo",
}

#: ``ctf/target`` is the framework-reserved bring-up anchor (a two-segment
#: standard-library name). The governor blesses it via the policy's reserved set,
#: exactly the mechanism the naming module provides for a shared standard library.
_POLICY = DEFAULT_POLICY.with_reserved("ctf/target")


def _load_ecosystem():
    """Import the real example plugins and snapshot their contributions.

    The docker target is used because it publishes every capability contract
    (including ``ctf/cap/network``), so ping and echo resolve and the graph is
    complete. Cataloguing never starts a container -- it only runs the setup
    hook that *registers* providers.
    """
    if not _CTF_EXAMPLES.is_dir():
        pytest.skip(f"CTF examples not found at {_CTF_EXAMPLES}")
    pytest.importorskip("docker", reason="docker SDK needed to import the docker target")
    if str(_CTF_EXAMPLES) not in sys.path:
        sys.path.insert(0, str(_CTF_EXAMPLES))

    from plugins import host
    from plugins.capabilities import ping
    from plugins.scenarios import echo
    from plugins.targets import docker as target_docker

    return collect(target_docker, host, ping, echo)


# ---------------------------------------------------------------------------
# 1. The defined contract: the healthy ecosystem audits clean.
# ---------------------------------------------------------------------------
def test_scenario_ecosystem_audits_clean():
    catalog = build_catalog(_load_ecosystem(), _POLICY)

    # No governance errors: every contract is single-sourced and resolvable.
    assert catalog.ok(), [f.message for f in catalog.errors()]

    by_name = {c.contract: c for c in catalog.contracts}

    # Every public contract the levels rely on is present and single-sourced.
    for contract in _PUBLIC_CONTRACTS:
        assert contract in by_name, f"missing public contract {contract!r}"
        assert len(by_name[contract].provided_by) == 1, contract

    # The public contracts are all well-namespaced (three-segment ctf/* names),
    # so they raise no namespace finding.
    for contract in _PUBLIC_CONTRACTS:
        assert validate_contract(contract, _POLICY) == [], contract


def test_scenario_contract_shape_is_pinned():
    """Pin the derived-capability wiring -- the contract's *shape*, not just names."""
    catalog = build_catalog(_load_ecosystem(), _POLICY)
    by_name = {c.contract: c for c in catalog.contracts}

    # The target anchor roots the graph at the ACQUIRED phase.
    assert by_name["ctf/target"].phase == "ACQUIRED"

    # ping is DERIVED: it must be required-consistent with host + network.
    ping = by_name["ctf/cap/ping"]
    assert ping.kind == "provider"
    # echo is DERIVED from exec: the scenario requires the exec capability.
    echo = by_name["ctf/scenario/echo"]
    assert echo.kind == "provider"
    exec_entry = by_name["ctf/cap/exec"]
    assert any("echo_via_exec" in r for r in exec_entry.required_by)
    assert any("ping_capability" in r for r in by_name["ctf/cap/network"].required_by)


# ---------------------------------------------------------------------------
# 2. Nothing may break it: each contract violation is caught.
# ---------------------------------------------------------------------------

# A rogue plugin that re-publishes an existing contract -> duplicate provider.
@provides("ctf/cap/exec")
def _rogue_exec():
    return object()


class _RogueDuplicateExec:
    __name__ = "rogue_duplicate_exec"

    def pytest_ctf_setup(self, registry, config):
        registry.register(_rogue_exec)


# A scenario written against a *renamed* (typo'd) capability contract -> dangling.
@provides("ctf/scenario/broken")
@requires("ctf/cap/exec_v2")  # someone renamed ctf/cap/exec and missed this
def _broken_scenario(shell):
    return object()


class _ScenarioAgainstRenamedContract:
    __name__ = "scenario_against_renamed_contract"

    def pytest_ctf_setup(self, registry, config):
        registry.register(_broken_scenario)


# A plugin publishing a mis-namespaced contract -> namespace violation.
@provides("Exec")  # not <org>/<domain>/<name>
def _badly_named_exec():
    return object()


class _MisNamespacedContract:
    __name__ = "mis_namespaced_contract"

    def pytest_ctf_setup(self, registry, config):
        registry.register(_badly_named_exec)


def _codes(catalog):
    return {f.code for f in catalog.findings}


def test_duplicate_provider_breaks_the_contract():
    ecosystem = _load_ecosystem()
    ecosystem.append(inspect_plugin(_RogueDuplicateExec()))
    catalog = build_catalog(ecosystem, _POLICY)

    assert not catalog.ok()
    assert "duplicate-provider" in _codes(catalog)
    offenders = [f for f in catalog.errors() if f.subject == "ctf/cap/exec"]
    assert offenders, "the duplicate must name the contract at fault"


def test_renamed_requirement_breaks_the_contract():
    ecosystem = _load_ecosystem()
    ecosystem.append(inspect_plugin(_ScenarioAgainstRenamedContract()))
    catalog = build_catalog(ecosystem, _POLICY)

    assert not catalog.ok()
    assert "unresolved" in _codes(catalog)
    dangling = [f for f in catalog.errors() if f.subject == "ctf/cap/exec_v2"]
    assert dangling, "the renamed requirement must surface as unresolved"


def test_misnamespaced_contract_is_flagged():
    ecosystem = _load_ecosystem()
    ecosystem.append(inspect_plugin(_MisNamespacedContract()))
    catalog = build_catalog(ecosystem, _POLICY)

    # A pure namespace issue is a warning, but the governor still reports it, so
    # a strict CI gate can reject it before it enters the ecosystem.
    assert "namespace" in _codes(catalog)
    flagged = [f for f in catalog.warnings() if f.subject == "Exec"]
    assert flagged


if __name__ == "__main__":
    catalog = build_catalog(_load_ecosystem(), _POLICY)
    print("Contracts in the scenario ecosystem:")
    for entry in catalog.contracts:
        print(
            f"  {entry.contract:22} {entry.kind:10} "
            f"phase={entry.phase or '-':9} <- {', '.join(entry.provided_by)}"
        )
    if catalog.findings:
        print("\nFindings:")
        for finding in catalog.findings:
            print(f"  [{finding.severity}] {finding.code}: {finding.message}")
    print("\nAudit OK" if catalog.ok() else "\nAudit FAILED")
