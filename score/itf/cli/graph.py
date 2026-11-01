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
"""`itf graph`: the topology (roles, factories, slots, scopes, shares) and the bring-up sequence (the goals'
actions in order, with after and breaks, and which steps a probe can skip) as Mermaid, from a resolved plan.
Metadata only: nothing is constructed."""

from __future__ import annotations

import re

from score.itf.core.engine.scopes import ROOT, display


def _id(text: str) -> str:
    return "n_" + re.sub(r"\W", "_", display(text))


def _text(text: str) -> str:
    return display(text).replace('"', "'")


def topology(session) -> str:
    plan = session._target_plan
    scopes = sorted({n.scope for n in plan.nodes if n.scope != ROOT} | {a.split(".")[0] for a, _ in plan.aliases})
    lines = ["flowchart LR"]

    def node_line(n) -> str:
        label = f"{n.name}<br/>{n.provider}<br/>{n.contract}"
        return f'{_id(n.ref)}["{_text(label)}"]'

    for node in plan.nodes:
        if node.scope == ROOT:
            lines.append(f"  {node_line(node)}")
    for scope in scopes:
        lines.append(f'  subgraph s_{scope}["scope {scope}"]')
        for node in plan.nodes:
            if node.scope == scope:
                lines.append(f"    {node_line(node)}")
        for alias, _ in plan.aliases:
            if alias.startswith(f"{scope}."):
                lines.append(f'    {_id(alias)}(["{_text(alias.split(".", 1)[1])}<br/>shared"])')
        lines.append("  end")
    for node in plan.nodes:
        for slot, provider in node.bindings:
            lines.append(f"  {_id(node.ref)} -->|{slot}| {_id(provider)}")
    for alias, target in plan.aliases:
        lines.append(f"  {_id(alias)} -.->|shares| {_id(target)}")
    return "\n".join(lines)


def sequence(session, action_label) -> str:
    plan = session._action_plan
    lines = ["flowchart TB"]
    steps = plan.steps if plan is not None else ()
    ids = {}
    goals = set(plan.goals) if plan is not None else set()
    for i, step in enumerate(steps, 1):
        ids[step.key] = f"s{i}"
        states = ", ".join(step.delivers)
        label = f"{i}. {states}<br/>{action_label(step)}"
        if step.probe:
            label += "<br/>probe: skipped when it holds"
            lines.append(f'  s{i}(["{_text(label)}"])')
        else:
            label += "<br/>no probe: always runs"
            lines.append(f'  s{i}["{_text(label)}"]')
        if goals & set(step.delivers):
            lines.append(f"  class s{i} goal")
    for assumed in plan.assumed if plan is not None else ():
        aid = "a_" + re.sub(r"\W", "_", assumed)
        lines.append(f'  {aid}{{{{"assumed: {_text(assumed)}"}}}}')
        for step in steps:
            if assumed in step.requires:
                lines.append(f"  {aid} -->|after {_text(assumed)}| {ids[step.key]}")
    for edge in plan.edges if plan is not None else ():
        if edge.before not in ids or edge.after not in ids:
            continue
        if edge.reason == "invalidates":
            lines.append(f"  {ids[edge.before]} -.->|breaks {_text(edge.state)}| {ids[edge.after]}")
        else:
            lines.append(f"  {ids[edge.before]} -->|after {_text(edge.state)}| {ids[edge.after]}")
    if goals:
        lines.append("  classDef goal stroke-width:3px")
    return "\n".join(lines)


def render_graph(session, kind: str, *, action_label) -> str:
    if kind == "topology":
        return topology(session)
    if kind == "sequence":
        return sequence(session, action_label)
    return "\n".join(
        [
            "```mermaid",
            "%% topology",
            topology(session),
            "```",
            "",
            "```mermaid",
            "%% sequence",
            sequence(session, action_label),
            "```",
        ]
    )
