"""Governance as a CTF plugin (dogfooding the ecosystem).

Governance is itself a CTF plugin: it hooks ``pytest_ctf_setup`` *last*, after
every other plugin has populated the registry, and checks the assembled
ecosystem against the namespacing policy.

Modes (ini ``ctf_governance``):

* ``off``    -- do nothing.
* ``warn``   -- emit a warning per violation (default).
* ``strict`` -- raise :class:`GovernanceViolation`. Because that derives from
  CTF's :class:`~ctf.errors.CompositionError`, the run stops *cleanly* through
  CTF's own error boundary (no ``INTERNALERROR``).
"""

from __future__ import annotations

import warnings

import pytest

from ctf.errors import CompositionError
from ctf.registry import Registry
from ctf_governance.naming import DEFAULT_POLICY, validate_contract

_INI = "ctf_governance"
_MODES = ("off", "warn", "strict")


class GovernanceViolation(CompositionError):
    """A contributed contract violates the governance policy."""


class CtfGovernanceWarning(UserWarning):
    """Emitted (in ``warn`` mode) for each governance violation."""


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addini(
        _INI,
        help="CTF governance mode: off | warn | strict",
        default="off",
    )


def _mode(config: pytest.Config | None) -> str:
    if config is None:
        return "off"
    mode = str(config.getini(_INI) or "off").strip().lower()
    return mode if mode in _MODES else "off"


def _violations(registry: Registry) -> list[str]:
    lines: list[str] = []
    for contract in sorted(registry.contracts()):
        issues = validate_contract(contract, DEFAULT_POLICY)
        if issues:
            lines.append(f"  {contract!r}: {'; '.join(issues)}")
    return lines


@pytest.hookimpl(trylast=True)
def pytest_ctf_setup(registry: Registry, config: pytest.Config) -> None:
    mode = _mode(config)
    if mode == "off":
        return
    lines = _violations(registry)
    if not lines:
        return
    message = "CTF governance: contracts violate the namespace policy:\n" + "\n".join(lines)
    if mode == "strict":
        raise GovernanceViolation(message)
    warnings.warn(message, CtfGovernanceWarning)


__all__ = ["GovernanceViolation", "CtfGovernanceWarning", "pytest_ctf_setup"]
