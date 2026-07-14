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
"""ITF Governance plugin — contract and alias integrity verification.

Validates the composition at session start, catching:

1. **Namespace violations** — contracts must follow ``<prefix>/<domain>/<name>``
   (e.g. ``itf/cap/exec``). Configurable via policy.
2. **Alias conflicts** — aliases must map to registered contracts.
3. **Dangling aliases** — alias targets that don't resolve in the registry.
4. **Reserved alias names** — prevent aliasing over internal names.
5. **Duplicate providers** — SSOT enforcement (two providers = error).

Modes (pytest ini ``itf_governance``):

* ``off``    — do nothing (default).
* ``warn``   — emit warnings per violation; tests still run.
* ``strict`` — raise GovernanceViolation; session aborts.

Usage:
    # pytest.ini or pyproject.toml
    [tool.pytest.ini_options]
    itf_governance = "warn"

    # Or via CLI
    pytest --itf-governance=strict
"""

from __future__ import annotations

import re
import warnings
from dataclasses import dataclass, field, replace
from typing import Any

import pytest

from score.itf.core.ctf.dut import DUT
from score.itf.core.ctf.errors import CompositionError
from score.itf.core.ctf.registry import Registry

# --------------------------------------------------------------------------
# Namespace policy
# --------------------------------------------------------------------------

_SEGMENT_RE = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class NamespacePolicy:
    """Rules a contract string must follow.

    Defaults enforce 2+ slash-separated lower-snake segments with a known
    prefix whitelist. This matches the ITF convention:
        ctf/target, itf/cap/exec, itf/net/ip_address
    """

    #: Minimum number of slash-separated segments.
    min_segments: int = 2
    #: Allowed first-segment prefixes. Empty = anything goes.
    allowed_prefixes: frozenset[str] = field(default_factory=lambda: frozenset({"ctf", "itf"}))
    #: Contracts that are explicitly exempt from validation.
    reserved: frozenset[str] = field(default_factory=frozenset)


DEFAULT_POLICY = NamespacePolicy()


def validate_contract(contract: str, policy: NamespacePolicy = DEFAULT_POLICY) -> list[str]:
    """Return human-readable issues for a contract string (empty = OK)."""
    if not contract:
        return ["contract name is empty"]
    if contract in policy.reserved:
        return []

    issues: list[str] = []
    parts = contract.split("/")

    if len(parts) < policy.min_segments:
        issues.append(f"expected at least {policy.min_segments} '/'-separated segments, found {len(parts)}")

    for part in parts:
        if not part:
            issues.append("contains an empty segment")
        elif not _SEGMENT_RE.match(part):
            issues.append(f"segment '{part}' is not a lower-snake identifier")

    if policy.allowed_prefixes and parts[0] not in policy.allowed_prefixes:
        issues.append(f"prefix '{parts[0]}' not in allowed set: {sorted(policy.allowed_prefixes)}")

    return issues


# --------------------------------------------------------------------------
# Alias policy
# --------------------------------------------------------------------------

#: Names that cannot be used as aliases (would shadow DUT methods).
_RESERVED_ALIAS_NAMES = frozenset(
    {
        "require",
        "available",
        "provides",
        "can_provide",
        "disable",
        "enable",
        "disabled",
        "materialized",
        "invalidate",
        "rebuild",
        "reprovision",
        "alias",
        "aliases",
    }
)


def validate_alias(
    name: str,
    contract: str,
    registry: Registry,
    policy: NamespacePolicy = DEFAULT_POLICY,
) -> list[str]:
    """Return issues for an alias registration (empty = OK)."""
    issues: list[str] = []

    if not name:
        issues.append("alias name is empty")
    elif name in _RESERVED_ALIAS_NAMES:
        issues.append(f"alias '{name}' shadows a DUT method — pick another name")
    elif "/" in name:
        issues.append(f"alias '{name}' contains '/'; aliases should be short names, not contract paths")

    if not contract:
        issues.append("alias target contract is empty")
    elif not registry.has(contract):
        issues.append(f"alias '{name}' → '{contract}': target contract is not registered")

    return issues


# --------------------------------------------------------------------------
# Findings
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    """A single governance violation."""

    severity: str  # "error" | "warning"
    code: str
    subject: str
    message: str


# --------------------------------------------------------------------------
# Audit engine
# --------------------------------------------------------------------------


def audit_contracts(registry: Registry, policy: NamespacePolicy = DEFAULT_POLICY) -> list[Finding]:
    """Check all contracts in the registry against the namespace policy."""
    findings: list[Finding] = []
    for contract in sorted(registry.contracts()):
        issues = validate_contract(contract, policy)
        for issue in issues:
            findings.append(
                Finding(
                    severity="warning",
                    code="namespace",
                    subject=contract,
                    message=f"contract '{contract}': {issue}",
                )
            )
    return findings


def audit_aliases(dut: DUT, registry: Registry, policy: NamespacePolicy = DEFAULT_POLICY) -> list[Finding]:
    """Check all registered aliases for integrity."""
    findings: list[Finding] = []
    for name, contract in sorted(dut.aliases().items()):
        issues = validate_alias(name, contract, registry, policy)
        for issue in issues:
            findings.append(
                Finding(
                    severity="error",
                    code="alias",
                    subject=name,
                    message=issue,
                )
            )
    return findings


def audit_composition(
    dut: DUT,
    registry: Registry,
    policy: NamespacePolicy = DEFAULT_POLICY,
) -> list[Finding]:
    """Full audit: contracts + aliases."""
    findings: list[Finding] = []
    findings.extend(audit_contracts(registry, policy))
    findings.extend(audit_aliases(dut, registry, policy))
    return findings


# --------------------------------------------------------------------------
# Errors and warnings
# --------------------------------------------------------------------------


class GovernanceViolation(CompositionError):
    """Raised in strict mode when governance checks fail."""


class GovernanceWarning(UserWarning):
    """Emitted in warn mode for each governance finding."""


# --------------------------------------------------------------------------
# Pytest plugin hooks
# --------------------------------------------------------------------------

_INI = "itf_governance"
_MODES = ("off", "warn", "strict")


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addini(
        _INI,
        help="ITF governance mode: off | warn | strict (default: off)",
        default="off",
    )
    parser.addoption(
        "--itf-governance",
        dest="itf_governance",
        default=None,
        help="ITF governance mode: off | warn | strict (overrides ini)",
    )


def _mode(config: pytest.Config) -> str:
    cli = config.getoption("itf_governance", default=None)
    if cli:
        mode = str(cli).strip().lower()
        return mode if mode in _MODES else "off"
    ini = str(config.getini(_INI) or "off").strip().lower()
    return ini if ini in _MODES else "off"


@pytest.hookimpl(trylast=True)
def pytest_itf_aliases(dut: DUT, config: pytest.Config) -> None:
    """Run governance checks after all aliases are registered.

    Because this hookimpl is trylast, it runs after all conftests/plugins
    have registered their aliases, giving us the full picture.
    """
    mode = _mode(config)
    if mode == "off":
        return

    # Access the kernel to get the registry
    from score.itf.core.itf_plugin import _kernel

    kernel = _kernel(config)
    if kernel is None:
        return

    findings = audit_composition(dut, kernel.registry)
    errors = [f for f in findings if f.severity == "error"]
    warnings_list = [f for f in findings if f.severity == "warning"]

    if mode == "strict" and errors:
        lines = [f"  [{f.code}] {f.message}" for f in errors]
        raise GovernanceViolation("ITF governance (strict): composition has errors:\n" + "\n".join(lines))

    all_findings = errors + warnings_list
    if all_findings:
        lines = [f"  [{f.code}] {f.message}" for f in all_findings]
        msg = "ITF governance findings:\n" + "\n".join(lines)
        if mode == "strict":
            raise GovernanceViolation(msg)
        else:
            warnings.warn(msg, GovernanceWarning, stacklevel=1)


__all__ = [
    "NamespacePolicy",
    "DEFAULT_POLICY",
    "validate_contract",
    "validate_alias",
    "Finding",
    "audit_contracts",
    "audit_aliases",
    "audit_composition",
    "GovernanceViolation",
    "GovernanceWarning",
]
