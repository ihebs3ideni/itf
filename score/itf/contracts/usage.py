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
"""The contract map: every contract name in use, from the loaded factories and actions and from tests.

`contract_map(parts, tests=None, definitions=None)` returns, per contract name, who offers it (label and the
members it publishes), who needs it (label and the members it expects), which tests ask for it, its definition
if there is one, and every disagreement between them. It reads declarations only (data), never runs anything.

`parts` is a catalog (anything with `.factories` and `.action_descs` dicts) or an iterable of factory and action
descriptors. `tests` is an iterable of requirements, or of `(test id, requirement)` pairs; a requirement has
`role`, `contract`, `shape`. `definitions` is a dict or a list of `Definition` (a list can hold two for one name).

`skeleton_from_usage(name, map)` builds a definition skeleton (a dict, ready for `yaml.safe_dump`) from the
shapes observed.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Disagreement:
    kind: str  # missing-member | missing-definition-member | two-definitions | major-mismatch
    message: str


@dataclass
class ContractEntry:
    name: str
    kind: str = "capability"
    offerers: list = field(default_factory=list)  # (label, members, major or None)
    needers: list = field(default_factory=list)  # (label, slot, expected members, major or None)
    tests: list = field(default_factory=list)  # (test id, role, members)
    definition: object = None
    definitions: list = field(default_factory=list)
    disagreements: list = field(default_factory=list)

    def to_json(self) -> dict:
        return {
            "contract": self.name,
            "kind": self.kind,
            "offered_by": [{"label": l, "shape": list(m), "major": mj} for l, m, mj in self.offerers],
            "needed_by": [{"label": l, "slot": s, "expects": list(m), "major": mj} for l, s, m, mj in self.needers],
            "tests": [{"test": t, "role": r, "shape": list(m)} for t, r, m in self.tests],
            "defined": self.definition is not None,
            "disagreements": [{"kind": d.kind, "message": d.message} for d in self.disagreements],
        }


def _members(shape) -> tuple[str, ...]:
    members = getattr(shape, "members", shape) or ()
    return tuple(sorted(getattr(m, "name", m) for m in members if not str(getattr(m, "name", m)).startswith("_")))


def _descriptors(parts) -> list:
    if hasattr(parts, "factories") and hasattr(parts, "action_descs"):
        return [*parts.factories.values(), *parts.action_descs.values()]
    return list(parts)


def _entry(found: dict, name: str, kind: str) -> ContractEntry:
    entry = found.setdefault(name, ContractEntry(name, kind))
    if kind == "state":
        entry.kind = "state"
    return entry


def contract_map(parts, tests=None, definitions=None) -> dict[str, ContractEntry]:
    found: dict[str, ContractEntry] = {}
    for part in _descriptors(parts):
        if hasattr(part, "contract"):  # a capability factory
            _entry(found, part.contract, "capability").offerers.append((part.label, _members(part.gives), part.major))
            for need in part.needs:
                major = part.need_majors.get(need.slot)
                _entry(found, need.contract, "capability").needers.append(
                    (part.label, need.slot, _members(need.expected), major)
                )
        else:  # an action
            _entry(found, part.state, "state").offerers.append((part.label, (), None))
            for other in part.also:
                _entry(found, other, "state").offerers.append((part.label, (), None))
            for state in part.after:
                _entry(found, state.rpartition(":")[2], "state").needers.append((part.label, "after", (), None))
            for need in part.uses:
                major = part.need_majors.get(need.slot)
                _entry(found, need.contract, "capability").needers.append(
                    (part.label, need.slot, _members(need.expected), major)
                )
    for item in tests or ():
        test_id, requirement = item if isinstance(item, tuple) else ("", item)
        if getattr(requirement, "contract", None):
            _entry(found, requirement.contract, "capability").tests.append(
                (test_id, requirement.role, tuple(requirement.shape or ()))
            )
    defs = list(definitions.values()) if isinstance(definitions, dict) else list(definitions or ())
    for definition in defs:
        entry = _entry(found, definition.contract, definition.kind)
        entry.definitions.append(definition)
        entry.definition = entry.definition or definition
    for entry in found.values():
        _compare(entry)
    return dict(sorted(found.items()))


def _compare(entry: ContractEntry) -> None:
    out = entry.disagreements
    if len(entry.definitions) > 1:
        where = ", ".join(d.source or "?" for d in entry.definitions)
        out.append(Disagreement("two-definitions", f"{entry.name} is defined {len(entry.definitions)} times: {where}"))
    offered = {m for _, members, _ in entry.offerers for m in members}
    if entry.offerers:
        for label, slot, expected, _ in entry.needers:
            for member in expected:
                if member not in offered:
                    out.append(
                        Disagreement(
                            "missing-member",
                            f"{label} (slot {slot}) expects {entry.name}.{member}, "
                            f"which no offerer has ({', '.join(l for l, _, _ in entry.offerers)})",
                        )
                    )
        for test_id, role, shape in entry.tests:
            for member in shape:
                if member not in offered:
                    out.append(
                        Disagreement(
                            "missing-member",
                            f"test {test_id or role} requires {entry.name}.{member}, which no offerer has",
                        )
                    )
    majors_offered = {m for _, _, m in entry.offerers if m is not None}
    for label, slot, _, major in entry.needers:
        if major is not None and majors_offered and major not in majors_offered:
            out.append(
                Disagreement(
                    "major-mismatch",
                    f"{label} (slot {slot}) expects {entry.name}@{major}, offered: "
                    f"{', '.join(f'@{m}' for m in sorted(majors_offered))}",
                )
            )
    if entry.definition is not None and entry.definition.kind == "capability":
        required = [m.name for m in entry.definition.members if m.required]
        for label, members, _ in entry.offerers:
            for member in required:
                if member not in members:
                    out.append(
                        Disagreement(
                            "missing-definition-member",
                            f"{label} offers {entry.name} without {member}, which its definition requires",
                        )
                    )
        for label, _, major in entry.offerers:
            if major is not None and major > entry.definition.version:
                out.append(
                    Disagreement(
                        "major-mismatch",
                        f"{label} offers {entry.name}@{major}, but the definition's version is {entry.definition.version}",
                    )
                )


def skeleton_from_usage(name: str, contracts: dict[str, ContractEntry]) -> dict:
    """A definition skeleton for `name`: the members observed (expected by needers and tests, published by
    offerers; the latter only are optional), the role most tests use, the major in use."""
    if name not in contracts:
        raise KeyError(f"{name!r} is not in use; contracts in use: {', '.join(contracts) or '(none)'}")
    entry = contracts[name]
    expected = {m for _, _, members, _ in entry.needers for m in members} | {
        m for _, _, members in entry.tests for m in members
    }
    published = sorted({m for _, members, _ in entry.offerers for m in members})
    members = [
        {"name": m, "signature": "TODO", "semantics": "TODO", **({} if m in expected else {"required": False})}
        for m in sorted(expected) + [m for m in published if m not in expected]
    ]
    roles = sorted({r for _, r, _ in entry.tests})
    majors = [m for _, _, m in entry.offerers if m is not None] + [m for _, _, _, m in entry.needers if m is not None]
    skeleton = {
        "contract": name,
        "kind": entry.kind,
        "version": max(majors, default=1),
        "summary": "TODO",
        "description": "TODO",
    }
    if entry.kind == "capability":
        if roles:
            skeleton["role"] = roles[0]
        if members:
            skeleton["members"] = members
    skeleton["guarantees"] = ["TODO"]
    return skeleton
