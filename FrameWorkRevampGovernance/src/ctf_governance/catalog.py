"""Ecosystem catalog and audit.

Given the per-plugin :class:`~ctf_governance.collector.Contribution` snapshots,
build a cross-plugin picture:

* **contracts** -- who provides each, who requires it, its phase;
* **points** -- every lifecycle extension point, its policy, its contributors;
* **findings** -- governance problems (duplicates, UNIQUE collisions, dangling
  requirements, namespace violations).

Nothing here executes user code; it only reasons over the collected snapshots.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ctf_governance.collector import Contribution
from ctf_governance.naming import DEFAULT_POLICY, NamespacePolicy, validate_contract

# Policies whose points accept at most one contributor across the whole
# ecosystem. Mirrors ctf.steps.BUILTIN_POINTS semantics without importing the
# enum values by identity.
_UNIQUE_POLICY = "UNIQUE"

ERROR = "error"
WARNING = "warning"


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    subject: str
    message: str


@dataclass(frozen=True)
class ContractEntry:
    contract: str
    kind: str  # "descriptor" | "provider" | "mixed"
    provided_by: tuple[str, ...]  # plugin names
    phase: str | None
    required_by: tuple[str, ...]  # "plugin:provider" that require this contract


@dataclass(frozen=True)
class PointEntry:
    point: str
    policy: str
    contributors: tuple[str, ...]  # "plugin:step"


@dataclass(frozen=True)
class Catalog:
    contracts: tuple[ContractEntry, ...]
    points: tuple[PointEntry, ...]
    findings: tuple[Finding, ...]

    def errors(self) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.severity == ERROR)

    def warnings(self) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.severity == WARNING)

    def ok(self) -> bool:
        return not self.errors()


def build_catalog(
    contributions: list[Contribution],
    policy: NamespacePolicy = DEFAULT_POLICY,
) -> Catalog:
    providers_by_contract: dict[str, list[str]] = {}
    descriptors_by_contract: dict[str, list[str]] = {}
    phase_by_contract: dict[str, str] = {}
    required_by: dict[str, list[str]] = {}
    points: dict[str, list[str]] = {}
    point_policy: dict[str, str] = {}

    for contribution in contributions:
        for contract, info in contribution.providers.items():
            providers_by_contract.setdefault(contract, []).append(contribution.plugin)
            phase_by_contract.setdefault(contract, info.phase)
            for req in info.requires:
                required_by.setdefault(req, []).append(
                    f"{contribution.plugin}:{info.name}"
                )
        for contract in contribution.descriptors:
            descriptors_by_contract.setdefault(contract, []).append(contribution.plugin)
        for point, names in contribution.steps.items():
            points.setdefault(point, []).extend(
                f"{contribution.plugin}:{name}" for name in names
            )
            point_policy[point] = contribution.policies.get(
                point, point_policy.get(point, "FANOUT")
            )

    contracts = _contract_entries(
        providers_by_contract, descriptors_by_contract, phase_by_contract, required_by
    )
    point_entries = tuple(
        PointEntry(point, point_policy.get(point, "FANOUT"), tuple(sorted(contribs)))
        for point, contribs in sorted(points.items())
    )
    findings = _audit(
        providers_by_contract,
        descriptors_by_contract,
        required_by,
        point_entries,
        policy,
    )
    return Catalog(contracts=contracts, points=point_entries, findings=findings)


def _contract_entries(providers, descriptors, phases, required_by) -> tuple[ContractEntry, ...]:
    entries: list[ContractEntry] = []
    for contract in sorted(set(providers) | set(descriptors)):
        prov = providers.get(contract, [])
        desc = descriptors.get(contract, [])
        if prov and desc:
            kind = "mixed"
        elif prov:
            kind = "provider"
        else:
            kind = "descriptor"
        entries.append(
            ContractEntry(
                contract=contract,
                kind=kind,
                provided_by=tuple(sorted(prov + desc)),
                phase=phases.get(contract),
                required_by=tuple(sorted(required_by.get(contract, []))),
            )
        )
    return tuple(entries)


def _audit(providers, descriptors, required_by, points, policy) -> tuple[Finding, ...]:
    findings: list[Finding] = []
    all_contracts = set(providers) | set(descriptors)

    # Duplicate providers: same contract offered by more than one source.
    for contract in sorted(all_contracts):
        sources = providers.get(contract, []) + descriptors.get(contract, [])
        if len(sources) > 1:
            findings.append(
                Finding(
                    ERROR,
                    "duplicate-provider",
                    contract,
                    f"contract {contract!r} is provided by {len(sources)} sources: "
                    f"{', '.join(sorted(sources))}",
                )
            )

    # Key collisions: a contract that is both a descriptor and a provider.
    for contract in sorted(set(providers) & set(descriptors)):
        findings.append(
            Finding(
                ERROR,
                "key-collision",
                contract,
                f"contract {contract!r} is published as a descriptor and also "
                "provided by a provider; a contract needs a single source",
            )
        )

    # Dangling requirements: a required contract nobody provides.
    for contract in sorted(required_by):
        if contract not in all_contracts:
            findings.append(
                Finding(
                    ERROR,
                    "unresolved",
                    contract,
                    f"contract {contract!r} is required by "
                    f"{', '.join(sorted(required_by[contract]))} but no plugin "
                    "provides it",
                )
            )

    # UNIQUE extension points contended by more than one contributor.
    for point in points:
        if point.policy == _UNIQUE_POLICY and len(point.contributors) > 1:
            findings.append(
                Finding(
                    ERROR,
                    "unique-collision",
                    point.point,
                    f"UNIQUE extension point {point.point!r} has "
                    f"{len(point.contributors)} contributors: "
                    f"{', '.join(point.contributors)}",
                )
            )

    # Namespace convention violations (warnings).
    for contract in sorted(all_contracts):
        issues = validate_contract(contract, policy)
        if issues:
            findings.append(
                Finding(
                    WARNING,
                    "namespace",
                    contract,
                    f"contract {contract!r}: {'; '.join(issues)}",
                )
            )

    return tuple(findings)


def audit(
    contributions: list[Contribution],
    policy: NamespacePolicy = DEFAULT_POLICY,
) -> Catalog:
    """Alias for :func:`build_catalog` that reads as an intent."""
    return build_catalog(contributions, policy)


__all__ = [
    "Finding",
    "ContractEntry",
    "PointEntry",
    "Catalog",
    "build_catalog",
    "audit",
    "ERROR",
    "WARNING",
]
