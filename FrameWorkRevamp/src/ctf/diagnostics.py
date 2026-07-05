"""Turn engine failures into clean, actionable diagnostics.

Composition is done *before any test runs*, while pytest is still starting the
session. A failure there means the test environment could not be assembled, so
the run cannot proceed -- but it must stop *cleanly*, with a message that points
at the plugin/contract at fault, rather than dumping an ``INTERNALERROR``
traceback that looks like a crash in the framework.

Two shapes of failure are distinguished:

* :class:`ctf.errors.CompositionError` -- the *ecosystem* is misconfigured
  (missing provider, duplicate, cycle, UNIQUE collision, ...). This is the
  user's/plugins' problem to fix; we render a sourced, hint-carrying message.
* Any other ``Exception`` -- an *internal* fault in CTF itself. We label it
  clearly as our bug and ask for a report, preserving the traceback.
"""

from __future__ import annotations

import traceback
from typing import Iterable, Mapping

from ctf.assembly import TierReport
from ctf.errors import (
    CompositionError,
    CyclicDependencyError,
    DuplicateProviderError,
    KeyCollisionError,
    StepCollisionError,
    StepExecutionError,
    UnresolvedContractError,
)

_BANNER = "CTF could not assemble the test environment; the run was stopped."

#: Per-error remediation hints, keyed by exception type.
_HINTS: dict[type[CompositionError], str] = {
    UnresolvedContractError: (
        "No enabled plugin provides this contract. Enable the plugin that "
        "provides it, or fix the contract name at the requiring side."
    ),
    DuplicateProviderError: (
        "Two plugins provide the same contract. Disable one of them, or move "
        "them behind distinct (namespaced) contract names."
    ),
    KeyCollisionError: (
        "A contract is published both as a descriptor (a fact) and by a "
        "provider (a factory). Choose one source of truth for it."
    ),
    CyclicDependencyError: (
        "Providers depend on each other in a cycle. Break the loop by removing "
        "one dependency or introducing an intermediate contract."
    ),
    StepCollisionError: (
        "This lifecycle extension point accepts exactly one contributor. "
        "Disable the extra plugin, or contribute to a FANOUT point instead."
    ),
    StepExecutionError: (
        "A plugin's setup step raised. This is a fault in that plugin, not in "
        "CTF; see the traceback below and fix the contributing step."
    ),
}


def format_composition_error(exc: CompositionError) -> str:
    """Render a user-facing diagnostic for an ecosystem misconfiguration."""
    kind = type(exc).__name__
    hint = _HINTS.get(type(exc), "")
    lines = [_BANNER, "", f"  {kind}: {exc}"]
    if hint:
        lines += ["", f"  hint: {hint}"]
    if isinstance(exc, StepExecutionError):
        tb = "".join(
            traceback.format_exception(
                type(exc.cause), exc.cause, exc.cause.__traceback__
            )
        )
        lines += ["", tb.rstrip()]
    return "\n".join(lines)


def format_internal_error(exc: BaseException) -> str:
    """Render a diagnostic for a fault inside CTF itself (our bug)."""
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    return (
        "INTERNAL CTF ERROR -- this is a bug in the framework, not in your "
        "configuration. Please report it with the traceback below.\n\n"
        f"  {type(exc).__name__}: {exc}\n\n"
        f"{tb}"
    )


def format_tier_walk(reports: Iterable[TierReport], unavailable: Mapping[str, str] | None = None) -> str:
    """Narrate a tier walk, tier by tier (first-class diagnostics).

    A tiered graph is hard to reason about when it breaks, so the engine tells
    the story of the bring-up: which contracts each tier realized, and -- when
    given -- which additive capabilities were skipped and why.
    """
    lines = ["CTF bring-up:"]
    for report in reports:
        realized = ", ".join(report.realized) if report.realized else "(nothing new)"
        lines.append(f"  [tier {report.tier}] {realized}")
    if unavailable:
        lines.append("  unavailable (skipped):")
        for contract in sorted(unavailable):
            lines.append(f"    - {contract}: {unavailable[contract]}")
    return "\n".join(lines)


__all__ = [
    "format_composition_error",
    "format_internal_error",
    "format_tier_walk",
]
