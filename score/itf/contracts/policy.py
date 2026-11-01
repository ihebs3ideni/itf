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
"""A project's rules over contracts, checked in a pipeline: `check(policy, contract_map, compositions)`.

A policy file (YAML, or a mapping):

    namespaces:           # contracts in these namespaces must have a definition (`acme` for acme/power.relay;
                          # a name without `/` is its first segment: `exec` for exec.command)
      - exec
      - platform
    roles:                # role -> the contract it must always be
      command: exec.command
      platform: platform.instance
    forbid_stability:     # no composition may use a contract defined with these stabilities
      - deprecated
    conformance: true     # every role of the given compositions passes its contract's conformance checks
                          # (`itf contracts check` runs them, as with --conformance)

`compositions` is an iterable of target plans, or of `(name, {role: contract})` pairs (`roles_of_plan` makes
those). `check` returns the violations; an empty list means the policy holds (the CLI exits 1 otherwise).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from .usage import ContractEntry

RULES = ("namespaces", "roles", "forbid_stability", "conformance")


def namespace_of(name: str) -> str:
    """`acme/power.relay` -> `acme`; a name without `/` -> its first segment (`exec.command` -> `exec`)."""
    return name.split("/", 1)[0] if "/" in name else name.split(".", 1)[0]


@dataclass(frozen=True)
class Violation:
    rule: str  # namespaces | roles | forbid_stability
    message: str


def roles_of_plan(plan) -> dict[str, str]:
    """`{role: contract}` of a target plan; a role of a scope is `scope.role`."""
    out = {}
    for node in plan.nodes:
        scope = "" if node.scope == "__itf_root__" else f"{node.scope}."
        out[f"{scope}{node.name}"] = node.contract
    return out


def _policy(policy) -> dict:
    if isinstance(policy, dict):
        data = policy
    else:
        data = yaml.safe_load(Path(policy).read_text(encoding="utf-8") if Path(str(policy)).is_file() else str(policy))
    data = data or {}
    unknown = sorted(set(data) - set(RULES))
    if unknown:
        raise ValueError(f"policy: unknown rule(s) {', '.join(unknown)}; the rules are {', '.join(RULES)}")
    return data


def check(policy, contracts: dict[str, ContractEntry], compositions=()) -> list[Violation]:
    rules = _policy(policy)
    found: list[Violation] = []
    for name, entry in contracts.items():
        if namespace_of(name) in (rules.get("namespaces") or ()) and entry.definition is None:
            found.append(Violation("namespaces", f"{name} is in use but has no definition"))
        stability = getattr(entry.definition, "stability", None)
        if stability in (rules.get("forbid_stability") or ()):
            found.append(Violation("forbid_stability", f"{name} is {stability}, which the policy forbids"))
    for item in compositions:
        label, roles = item if isinstance(item, tuple) else ("composition", roles_of_plan(item))
        for role, contract in sorted(roles.items()):
            wanted = (rules.get("roles") or {}).get(role.rpartition(".")[2])
            if wanted is not None and wanted != contract:
                found.append(
                    Violation("roles", f"{label}: role {role} is {contract}, the policy says it is always {wanted}")
                )
    return found


def load_policy(policy) -> dict:
    """The rules of a policy file (or mapping); an unknown rule is an error naming the known ones."""
    return _policy(policy)
