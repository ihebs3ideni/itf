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
"""The target handle: one per session, a thin view over the realization
(docs/octo-kit/12-spec-itf-core.md §4).

`target.x` is a node of the root scope, `target.dev1.x` a node of device scope `dev1`. A device
never falls back to the root: what `dev1` should share, its recipe aliases (`dev1.alias("x", ".x")`).
Aliased names share the underlying node rather than creating another instance.
"""

from __future__ import annotations

from .engine.bringup import observe
from .engine.config import redact_target
from .engine.scopes import ROOT, TARGET_MEMBERS, VIEW_MEMBERS, display_json


# The handle is a view, not a store: attribute access fetches (lazily constructing) the node from the
# realization, so `renew` can swap an object and the next `target.x` simply sees the new one.
class ScopeView:
    def __init__(self, session, scope: str):
        self._scope = scope
        self._session = session

    @property
    def scope(self) -> str | None:
        """The device scope's name; `None` for the target's root."""
        return None if self._scope == ROOT else self._scope

    @property
    def _label(self) -> str:
        return "target" if self._scope == ROOT else f"target.{self._scope}"

    def tokens(self) -> tuple[str, ...]:
        return self._session._target_plan.tokens(self._scope)

    def has(self, token: str) -> bool:
        return token in self.tokens()

    def names(self) -> tuple[str, ...]:
        return self._session._target_plan.names(self._scope)

    def get(self, name: str):
        if name not in self.names():
            raise KeyError(f"{self._label} has no {name!r}; known: {', '.join(self.names()) or '(nothing)'}")
        return self._session._realization.get(f"{self._scope}.{name}")

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            return self.get(name)
        except KeyError as exc:
            raise AttributeError(str(exc)) from exc

    def __repr__(self) -> str:
        return f"<{self._label}: {', '.join(self.names()) or '(no nodes)'}>"

    def states(self) -> frozenset[str]:
        """States held at the last probe, restricted to this scope, unqualified."""
        prefix = f"{self._scope}:"
        return frozenset(s[len(prefix) :] for s in self._session._last_observed if s.startswith(prefix))

    def probe(self, *states: str) -> frozenset[str]:
        prefix = f"{self._scope}:"
        wanted = frozenset(f"{prefix}{s}" for s in states) if states else None
        session = self._session
        meter = session._meter()
        observation = observe(
            session._full_plan, session._realization, states=wanted, observer=meter, resolver=session._resolver
        )
        session._record_probes("target_probe", meter)
        self._session._last_observed = (
            self._session._last_observed - {s for s in self._session._last_observed if s.startswith(prefix)}
        ) | observation.holds
        return frozenset(s[len(prefix) :] for s in observation.holds if s.startswith(prefix))

    def reach(self, *states: str, assume: tuple[str, ...] = (), reason: str = "", owner: str = ""):
        """`session.reach` with unqualified states and assumptions taken to mean this scope."""
        q = lambda s: s if ":" in s else f"{self._scope}:{s}"
        return self._session.reach(*map(q, states), assume=tuple(map(q, assume)), reason=reason, owner=owner)

    def renew(self, *names: str):
        """`session.renew` with bare node names taken to mean this scope (`.name` is the root)."""
        q = lambda n: n if n.startswith(".") or "." in n else f"{self._scope}.{n}"
        return self._session.renew(*map(q, names))

    def plan(self) -> dict:
        tp = _redacted(self._session)
        ap = self._session._action_plan
        return display_json(
            {
                "target": {k: v for k, v in tp.to_json().items() if k != "nodes"}
                | {"nodes": [n for n in tp.to_json()["nodes"] if n["scope"] == self._scope]},
                "action": {k: v for k, v in ap.to_json().items() if k != "steps"}
                | {
                    "steps": [
                        s for s in ap.to_json()["steps"] if any(d.startswith(f"{self._scope}:") for d in s["delivers"])
                    ]
                },
            }
        )


class Target(ScopeView):
    """The whole target: the root scope's nodes as attributes, each device scope as `target.<name>`."""

    def __init__(self, session, scopes):
        super().__init__(session, ROOT)
        self._scopes = {name: ScopeView(session, name) for name in sorted(scopes)}

    def scopes(self) -> tuple[str, ...]:
        return tuple(self._scopes)

    def get(self, name: str):
        if name in self._scopes and name not in self.names():
            raise KeyError(f"{name!r} is a device scope, not a node: use target.{name}")
        return super().get(name)

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        if name in self._scopes:
            return self._scopes[name]
        if name in self.names():
            return self.get(name)
        raise AttributeError(
            f"target has no node or scope {name!r}; nodes: {', '.join(self.names()) or '(none)'}; "
            f"scopes: {', '.join(self._scopes) or '(none)'}"
        )

    def __repr__(self) -> str:
        return (
            f"<target: {', '.join(self.names()) or '(no nodes)'}"
            f"{'; scopes: ' + ', '.join(self._scopes) if self._scopes else ''}>"
        )

    def plan(self) -> dict:
        return {
            "target": target_view(_redacted(self._session), self._scopes),
            "action": display_json(self._session._action_plan.to_json()),
        }


def _redacted(session):
    return redact_target(session._target_plan, getattr(session._catalog, "config_schemas", {}))


def target_view(target_plan, scopes=()) -> dict:
    """The target plan shaped like the handle: root nodes, then one entry per device scope."""
    data = target_plan.to_json()
    nodes = data.pop("nodes")
    root = [n for n in nodes if n["scope"] == ROOT]
    by_scope: dict = {name: {"nodes": []} for name in scopes}
    for n in nodes:
        if n["scope"] != ROOT:
            by_scope.setdefault(n["scope"], {"nodes": []})["nodes"].append(n)
    return display_json({"nodes": root, "scopes": dict(sorted(by_scope.items())), **data})


def name_clashes(target_plan, scopes) -> tuple[str, ...]:
    """Names `target.<x>` / `target.<scope>.<x>` could not resolve unambiguously."""
    clashes = []
    root_names = set(target_plan.names(ROOT))
    for name in sorted(root_names & set(scopes)):
        clashes.append(f"target.{name} is both a root node and a device scope")
    for name in sorted(root_names & TARGET_MEMBERS):
        clashes.append(f"target.{name} shadows the handle's own member {name!r}")
    for scope in sorted(scopes):
        for name in sorted(set(target_plan.names(scope)) & VIEW_MEMBERS):
            clashes.append(f"target.{scope}.{name} shadows the handle's own member {name!r}")
    return tuple(clashes)
