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
"""The composition format: one YAML document says what a target is made of.

    include:                        # merged first, in order; this file wins
      - base.itf.yaml
    capabilities:                   # keyed by role: the name tests use (`target.command`)
      platform:
        factory: acme.platform    # <pack>.<capability factory>
        with:                       # the factory's settings, checked against its config dataclass
          image: my-image:latest
      command: acme.exec            # short form: just the factory
      shell:
        factory: acme.shell
        bind:                       # only when a slot has more than one candidate: slot -> role
          endpoint: lab_endpoint
    goals:                          # state contracts to reach; nothing is inferred
      - platform.up
      - state: console.open
        by: acme.open               # only when two listed packs have an action making it true
    relations:                      # a third party's temporal relations between states, added to the actions' own
      - state: platform.up          # an action of a listed pack makes this true
        after:                      # ... only once these hold
          - console.open
        breaks:                     # ... and it destroys these
          - network.reachable
    assume:
      - state: rack.ready
        owner: lab
        reason: the rack keeps it on
    scopes:                         # one more device of a multi-device target
      gw:
        capabilities:
          command: acme.exec
        goals:
          - shell.open
        relations:                  # same entries; `state` and its `after`/`breaks` are in this scope
          - state: shell.open
            after:
              - platform.up
        share:
          - platform                # gw uses the root's platform role

An override file is a composition holding only what changes; it is merged by role like an include, after
the target. `${NAME}` / `${NAME:-default}` in a `with:` value reads the environment (`$${` is a literal
`${`); a value that is exactly one reference is read as a YAML scalar, so `port: ${SSH_PORT:-22}` is an int.

Translation to the engine is direct: role = node name, factory = provider, `with` = config, `bind` = bindings
by role, `share` = an alias to the root role, goals = goal claims, `by` = the chosen action, `relations` = the listed state's `after` and `breaks` added to the claim of the action
that makes it true (a state no listed action makes or assumes is a compile error). The actions
considered are those of the packs of the listed factories plus the project's own; a goal that two of them could
make true, with no `by`, is a compile error naming both. No capability enters a target unless the composition
lists it.
"""

from __future__ import annotations

import copy
import dataclasses
import os
import re
from pathlib import Path
from typing import Any, Mapping

import yaml

from ..engine.packs import pack_of
from ..engine.publish import Catalog
from ..engine.scopes import ROOT, check_scope_name, node_ref, state_ref
from ..octo import AssumeClaim, GoalClaim, NodeClaim, StateContractClaim

COMPOSITION_ORIGIN = "composition"
KEYS = ("include", "packs", "capabilities", "goals", "relations", "assume", "scopes")
SCOPE_KEYS = ("capabilities", "goals", "relations", "share")
RELATION_KEYS = ("state", "after", "breaks")
ENTRY_KEYS = ("factory", "with", "bind", "remove")


class CompositionError(ValueError):
    """The composition cannot be compiled; the message names what is wrong and what to write instead."""


# ---- reading and merging ------------------------------------------------------------------------------------


def read(source: Any) -> tuple[Mapping[str, Any], Path | None]:
    """`source` as (document, path-or-None): a parsed mapping, a path, or inline YAML/JSON text."""
    if isinstance(source, Mapping):
        return source, None
    value = getattr(source, "value", source)
    try:
        candidate = Path(value)
        path = candidate if candidate.is_file() else None
    except (OSError, ValueError):
        path = None  # multiline text cannot be stat()'d as a path
    try:
        if path is not None:
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        else:
            doc = yaml.safe_load(str(value))
    except yaml.YAMLError as exc:
        raise CompositionError(f"{path or 'composition'} is not valid YAML: {exc}") from exc
    doc = doc or {}
    if not isinstance(doc, Mapping):
        raise CompositionError(f"{path or 'composition'}: a composition is a mapping, not {type(doc).__name__}")
    return doc, (path.resolve() if path is not None else None)


def _entry(role: str, entry: Any, where: str) -> dict:
    if entry is None:
        return {}
    if isinstance(entry, str):
        return {"factory": entry}
    if isinstance(entry, Mapping):
        unknown = sorted(set(entry) - set(ENTRY_KEYS))
        if unknown:
            raise CompositionError(
                f"{where}: role {role!r} has unknown key(s) {', '.join(unknown)}; a role has {', '.join(ENTRY_KEYS)}"
            )
        for key in ("with", "bind"):
            if entry.get(key) is not None and not isinstance(entry[key], Mapping):
                raise CompositionError(f"{where}: role {role!r}: {key} is a mapping")
        if "remove" in entry and (entry["remove"] is not True or len(entry) > 1):
            raise CompositionError(f"{where}: role {role!r}: `remove: true` stands alone; it takes the role out")
        return {k: copy.deepcopy(v) for k, v in entry.items() if v is not None}
    raise CompositionError(f"{where}: role {role!r} is `<pack>.<factory>` or a mapping, not {entry!r}")


def _capabilities(value: Any, where: str) -> dict:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise CompositionError(f"{where}: capabilities is a mapping of role to factory")
    return {str(role): _entry(str(role), entry, where) for role, entry in value.items()}


def _goal(goal: Any, where: str) -> dict:
    if isinstance(goal, str):
        return {"state": goal}
    if isinstance(goal, Mapping) and isinstance(goal.get("state"), str) and set(goal) <= {"state", "by"}:
        return dict(goal)
    raise CompositionError(f"{where}: a goal is a state name, or `state:` with an optional `by:`; not {goal!r}")


def _names(value: Any, where: str, key: str, state: str) -> list:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise CompositionError(f"{where}: relation of {state!r}: {key} is a list of state names")
    return list(value)


def _relation(item: Any, where: str) -> dict:
    if not (isinstance(item, Mapping) and isinstance(item.get("state"), str) and set(item) <= set(RELATION_KEYS)):
        raise CompositionError(
            f"{where}: a relation is `state:` with `after:` and/or `breaks:` (lists of states); not {item!r}"
        )
    state = item["state"]
    after, breaks = (_names(item.get(key), where, key, state) for key in ("after", "breaks"))
    if not after and not breaks:
        raise CompositionError(f"{where}: relation of {state!r} has neither `after` nor `breaks`")
    return {"state": state, "after": after, "breaks": breaks}


def _merge_relations(base: list, extra: list) -> list:
    """By state; the lists of one state are joined, so an include and its includer both add."""
    merged = {
        item["state"]: {"state": item["state"], "after": list(item["after"]), "breaks": list(item["breaks"])}
        for item in base
    }
    for item in extra:
        mine = merged.setdefault(item["state"], {"state": item["state"], "after": [], "breaks": []})
        for key in ("after", "breaks"):
            mine[key] = list(dict.fromkeys([*mine[key], *item[key]]))
    return list(merged.values())


def _assume(item: Any, where: str) -> dict:
    entry = {"state": item} if isinstance(item, str) else item
    if not (
        isinstance(entry, Mapping)
        and isinstance(entry.get("state"), str)
        and set(entry) <= {"state", "owner", "reason"}
    ):
        raise CompositionError(f"{where}: an assumption is `state:` with optional `owner:` and `reason:`; not {item!r}")
    return dict(entry)


def _by_state(base: list, extra: list) -> list:
    merged = {item["state"]: item for item in base}
    for item in extra:
        merged[item["state"]] = {**merged.get(item["state"], {}), **item}
    return list(merged.values())


def _merge_caps(base: dict, over: dict) -> dict:
    out = {role: dict(entry) for role, entry in base.items()}
    for role, entry in over.items():
        if entry.get("remove"):
            # An override or includer takes the role out; the marker travels on until the final merge, since a
            # file is first merged over an empty base where there is nothing to remove yet.
            if role in out and not out[role].get("remove"):
                out.pop(role)
            else:
                out[role] = {"remove": True}
            continue
        mine = out.setdefault(role, {})
        if "factory" in entry and entry["factory"] != mine.get("factory"):
            mine.clear()  # another factory: the old one's settings and bindings do not carry over
        for key, value in entry.items():
            mine[key] = {**mine.get(key, {}), **value} if key in ("with", "bind") else value
    return out


def _scope(scope: Any, name: str, where: str) -> dict:
    if scope is None:
        scope = {}
    if not isinstance(scope, Mapping):
        raise CompositionError(f"{where}: scope {name!r} is a mapping")
    unknown = sorted(set(scope) - set(SCOPE_KEYS))
    if unknown:
        raise CompositionError(
            f"{where}: scope {name!r} has unknown key(s) {', '.join(unknown)}; it has {', '.join(SCOPE_KEYS)}"
        )
    share = scope.get("share") or []
    if not isinstance(share, list) or not all(isinstance(s, str) for s in share):
        raise CompositionError(f"{where}: scope {name!r}: share is a list of root role names")
    return {
        "capabilities": _capabilities(scope.get("capabilities"), where),
        "goals": [_goal(g, where) for g in scope.get("goals") or ()],
        "relations": [_relation(r, where) for r in scope.get("relations") or ()],
        "share": list(share),
    }


def _packs(value: Any, where: str) -> dict:
    """`packs:` names where a pack that is not installed lives: pack name -> module of its entrypoint."""
    if value is None:
        return {}
    if not isinstance(value, Mapping) or not all(isinstance(k, str) and isinstance(v, str) for k, v in value.items()):
        raise CompositionError(f"{where}: packs maps a pack name to the module of its entrypoint (acme: acme.plugin)")
    return dict(value)


def _normalise(doc: Mapping, where: str) -> dict:
    unknown = sorted(set(doc) - set(KEYS))
    if unknown:
        raise CompositionError(f"{where}: unknown key(s) {', '.join(unknown)}; a composition has {', '.join(KEYS)}")
    scopes = doc.get("scopes") or {}
    if not isinstance(scopes, Mapping):
        raise CompositionError(f"{where}: scopes is a mapping of name to scope")
    return {
        "packs": _packs(doc.get("packs"), where),
        "capabilities": _capabilities(doc.get("capabilities"), where),
        "goals": [_goal(g, where) for g in doc.get("goals") or ()],
        "relations": [_relation(r, where) for r in doc.get("relations") or ()],
        "assume": [_assume(a, where) for a in doc.get("assume") or ()],
        "scopes": {str(n): _scope(s, str(n), where) for n, s in scopes.items()},
    }


def _merge(base: dict, over: dict) -> dict:
    scopes = {n: dict(s) for n, s in base["scopes"].items()}
    for name, scope in over["scopes"].items():
        mine = scopes.setdefault(name, {"capabilities": {}, "goals": [], "relations": [], "share": []})
        scopes[name] = {
            "capabilities": _merge_caps(mine["capabilities"], scope["capabilities"]),
            "goals": _by_state(mine["goals"], scope["goals"]),
            "relations": _merge_relations(mine["relations"], scope["relations"]),
            "share": list(dict.fromkeys([*mine["share"], *scope["share"]])),
        }
    return {
        "packs": {**base["packs"], **over["packs"]},
        "capabilities": _merge_caps(base["capabilities"], over["capabilities"]),
        "goals": _by_state(base["goals"], over["goals"]),
        "relations": _merge_relations(base["relations"], over["relations"]),
        "assume": _by_state(base["assume"], over["assume"]),
        "scopes": scopes,
    }


EMPTY = {"packs": {}, "capabilities": {}, "goals": [], "relations": [], "assume": [], "scopes": {}}


def load(source: Any, *, _seen: frozenset = frozenset()) -> dict:
    """One effective document: `include`s merged first (in order), then the file itself, which wins."""
    doc, path = read(source)
    where = str(path) if path is not None else "composition"
    if path is not None:
        if path in _seen:
            raise CompositionError(f"include cycle at {path}")
        _seen = _seen | {path}
    includes = doc.get("include") or []
    if isinstance(includes, str):
        includes = [includes]
    effective = copy.deepcopy(EMPTY)
    for name in includes:
        target = (path.parent / name) if path is not None else Path(name)
        if path is not None and not target.exists() and Path(name).is_file():
            target = Path(name)  # a generated parent, named by its path from the working directory
        if not target.is_file():
            raise CompositionError(f"{where}: include {name!r} is not a file (looked for {target})")
        effective = _merge(effective, load(target, _seen=_seen))
    return _merge(effective, _normalise(doc, where))


def load_all(target: Any, overrides=()) -> dict:
    """The target with every override file merged over it by role, in order; removed roles are gone."""
    doc = load(target)
    for override in overrides:
        doc = _merge(doc, load(override))
    return _without_removed(doc)


def _without_removed(doc: dict) -> dict:
    keep = lambda caps: {r: e for r, e in caps.items() if not e.get("remove")}  # noqa: E731
    return {
        **doc,
        "capabilities": keep(doc["capabilities"]),
        "scopes": {n: {**s, "capabilities": keep(s["capabilities"])} for n, s in doc["scopes"].items()},
    }


# ---- environment values ---------------------------------------------------------------------------------------

_ENV_REF = re.compile(r"\$(\$)?\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


def _expand(value: Any, where: str) -> Any:
    if not isinstance(value, str) or "${" not in value:
        return value

    def substitute(match: re.Match) -> str:
        escaped, name, default = match.groups()
        if escaped:
            return match.group(0)[1:]
        if name in os.environ:
            return os.environ[name]
        if default is not None:
            return default
        raise CompositionError(f"{where} references ${{{name}}}, which is not set")

    whole = _ENV_REF.fullmatch(value)
    expanded = _ENV_REF.sub(substitute, value)
    if whole and not whole.group(1):
        return yaml.safe_load(expanded) if expanded else expanded
    return expanded


# ---- compiling ------------------------------------------------------------------------------------------------


def factory_labels(doc: Mapping) -> tuple[str, ...]:
    """Every factory label the composition names, in every scope."""
    caps = [doc["capabilities"], *(s["capabilities"] for s in doc["scopes"].values())]
    labels = tuple(dict.fromkeys(e["factory"] for c in caps for e in c.values() if "factory" in e))
    for label in labels:
        if not isinstance(label, str) or "." not in label.strip("."):
            raise CompositionError(f"{label!r} is not a capability factory label; write it as <pack>.<name>")
    return labels


def pack_modules(doc: Mapping) -> dict:
    """The composition's `packs:`: where packs that are not installed live."""
    return dict(doc.get("packs") or {})


def packs_of(doc: Mapping) -> tuple[str, ...]:
    return tuple(dict.fromkeys(pack_of(label) for label in factory_labels(doc)))


@dataclasses.dataclass(frozen=True)
class Compiled:
    setup: frozenset  # node claims
    init: frozenset  # goal, assumption and chosen-action claims
    roles: dict  # scope -> {role: factory label}
    pins: dict  # (scope, state) -> action label


def _unknown_label(label: str, catalog: Catalog, kind: str, where: str) -> CompositionError:
    pack = pack_of(label)
    table = catalog.factories if kind == "factory" else catalog.action_descs
    same = sorted(l for l in table if pack_of(l) == pack)
    if same:
        hint = f"pack {pack} has: {', '.join(same)}"
    else:
        hint = f"no loaded pack is named {pack!r}; loaded: {', '.join(catalog.packs()) or '(none)'}"
    what = "capability factory" if kind == "factory" else "action"
    return CompositionError(f"{where}: {label!r} is not a known {what}; {hint}")


def _scope_name(name: str) -> str:
    return ROOT if name == ROOT else check_scope_name(name)


def compile(doc: Mapping, catalog: Catalog) -> Compiled:
    """Translate an effective document into claims, checking everything the engine cannot say in these terms."""
    setup: set = set()
    roles: dict[str, dict] = {}
    scopes = {
        ROOT: {"capabilities": doc["capabilities"], "goals": doc["goals"], "relations": doc["relations"], "share": []}
    }
    for name, scope in doc["scopes"].items():
        scopes[_scope_name(name)] = scope

    for scope_name, scope in scopes.items():
        shown = "" if scope_name == ROOT else f"scope {scope_name}: "
        mine = roles.setdefault(scope_name, {})
        for role, entry in scope["capabilities"].items():
            where = f"{shown}role {role!r}"
            if not role.isidentifier() or role.startswith("_"):
                raise CompositionError(f"{where}: a role is a Python identifier (it becomes target.{role})")
            label = entry.get("factory")
            if label is None:
                raise CompositionError(
                    f"{where}: no factory; write `{role}: <pack>.<factory>` or give `factory:` "
                    "(an override file may only change a role the target already has)"
                )
            if label not in catalog.factories:
                raise _unknown_label(label, catalog, "factory", where)
            factory = catalog.factories[label]
            slots = {n.slot for n in factory.needs}
            bind = entry.get("bind") or {}
            stray = sorted(set(bind) - slots)
            if stray:
                raise CompositionError(
                    f"{where}: {label} has no slot {', '.join(map(repr, stray))}; its slots are: "
                    f"{', '.join(sorted(slots)) or '(none)'}"
                )
            with_ = {k: _expand(v, f"{where} with {k!r}") for k, v in (entry.get("with") or {}).items()}
            mine[role] = label
            setup.add(
                NodeClaim(
                    scope=scope_name,
                    name=role,
                    using=label,
                    bind=tuple(sorted(bind.items())),
                    config=tuple(sorted(with_.items())),
                    origin=COMPOSITION_ORIGIN,
                )
            )
        for role in scope["share"]:
            if role not in doc["capabilities"]:
                raise CompositionError(
                    f"{shown}share names {role!r}, which is not a role of the root; roles: "
                    f"{', '.join(doc['capabilities']) or '(none)'}"
                )
            mine[role] = roles[ROOT].get(role) if ROOT in roles else None
            setup.add(NodeClaim(scope=scope_name, name=role, alias=node_ref(f".{role}"), origin=COMPOSITION_ORIGIN))

    init, pins = _compile_states(doc, scopes, roles, catalog)
    return Compiled(frozenset(setup), frozenset(init), roles, pins)


def _compile_states(doc, scopes, roles, catalog: Catalog):
    listed = {pack_of(label) for per_scope in roles.values() for label in per_scope.values() if label} | {"project"}
    considered = {l: d for l, d in catalog.action_descs.items() if d.pack in listed}
    by_token: dict[str, list[str]] = {}
    for label in sorted(considered):
        for claim in catalog.action_claims[label]:
            for token in (claim.token, *claim.also_delivers):
                if label not in by_token.setdefault(token, []):
                    by_token[token].append(label)

    pins: dict[tuple, str] = {}
    init: set = set()
    for scope_name, scope in scopes.items():
        shown = "" if scope_name == ROOT else f"scope {scope_name}: "
        goals = []
        for goal in scope["goals"]:
            goals.append(goal["state"])
            by = goal.get("by")
            if by is not None:
                if by not in catalog.action_descs:
                    raise _unknown_label(by, catalog, "action", f"{shown}goal {goal['state']!r}")
                if by not in considered:
                    raise CompositionError(
                        f"{shown}goal {goal['state']!r}: by {by!r}, but pack {pack_of(by)!r} is not in the "
                        f"composition; list a capability of that pack"
                    )
                if by not in by_token.get(goal["state"], ()):
                    raise CompositionError(
                        f"{shown}goal {goal['state']!r}: {by} does not make it true; "
                        f"candidates: {', '.join(by_token.get(goal['state'], ())) or '(none listed)'}"
                    )
                pins[(scope_name, goal["state"])] = by
        if goals:
            init.add(GoalClaim(scope=scope_name, states=frozenset(goals), origin=COMPOSITION_ORIGIN))

    ambiguous = {t for t, labels in by_token.items() if len(labels) > 1}
    assumed = {item["state"] for item in doc["assume"]}
    # Walk what each scope reaches from its goals; a state two actions could make true needs a `by`.
    for scope_name, scope in scopes.items():
        seen: set = set()
        work = [(scope_name, g["state"]) for g in scope["goals"]]
        while work:
            where, token = work.pop()
            if (where, token) in seen or (where == ROOT and token in assumed):
                continue
            seen.add((where, token))
            labels = by_token.get(token, [])
            if token in ambiguous:
                chosen = pins.get((where, token))
                if chosen is None:
                    shown = "" if where == ROOT else f" in scope {where}"
                    raise CompositionError(
                        f"state {token!r}{shown} can be made true by {' or '.join(labels)}; say which with\n"
                        f"    - state: {token}\n      by: <one of: {', '.join(labels)}>"
                    )
                labels = [chosen]
            for label in labels:
                for claim in catalog.action_claims[label]:
                    for ref in claim.requires:
                        ref_scope, _, ref_token = ref.rpartition(":")
                        work.append((ref_scope or where, ref_token))

    # Claims this composition writes for one scope: the action chosen with `by`, with the relations it adds.
    overrides: dict[tuple, StateContractClaim] = {}
    for (scope_name, token), label in sorted(pins.items()):
        claims = catalog.action_claims[label]
        base = next((c for c in claims if c.token == token), claims[0])
        overrides[(scope_name, token)] = dataclasses.replace(
            base, token=token, scope=scope_name, origin=COMPOSITION_ORIGIN
        )
    _apply_relations(scopes, assumed, by_token, ambiguous, pins, overrides, catalog)
    init.update(overrides.values())
    for label, desc in considered.items():
        for claim in catalog.action_claims[label]:
            if claim.token not in ambiguous:
                init.add(claim)
    for item in doc["assume"]:
        init.add(
            AssumeClaim(
                scope=ROOT,
                token=item["state"],
                owner=item.get("owner", ""),
                reason=item.get("reason", ""),
                origin=COMPOSITION_ORIGIN,
            )
        )
    return init, pins


def _made_or_assumed(ref: str, scope_name: str, by_token: dict, assumed: set, shown: str, where: str) -> str:
    """The token of a state a relation names: it must be made by a listed action or assumed."""
    scope, _, token = state_ref(ref).rpartition(":")
    if token in by_token or (token in assumed and (scope or scope_name) == ROOT):
        return token
    listed = sorted({*by_token, *assumed})
    raise CompositionError(
        f"{shown}{where}: no listed action makes {token!r} true and it is not assumed; "
        f"states the listed packs make: {', '.join(listed) or '(none)'}"
    )


def _apply_relations(scopes, assumed, by_token, ambiguous, pins, overrides, catalog: Catalog) -> None:
    """Add each relation's `after` and `breaks` to the claim of the action that makes its `state` true."""
    for scope_name, scope in scopes.items():
        shown = "" if scope_name == ROOT else f"scope {scope_name}: "
        for relation in scope["relations"]:
            state = relation["state"]
            where = f"relation of {state!r}"
            token = _made_or_assumed(state, scope_name, by_token, assumed, shown, where)
            for ref in (*relation["after"], *relation["breaks"]):
                _made_or_assumed(ref, scope_name, by_token, assumed, shown, where)
            labels = by_token.get(token, [])
            if not labels:
                raise CompositionError(
                    f"{shown}{where}: {token!r} is only assumed, so no action runs to be ordered; "
                    "put the relation on the action that needs it"
                )
            label = pins.get((scope_name, token))
            if label is None:
                if len(labels) > 1:
                    raise CompositionError(
                        f"{shown}{where}: {token!r} can be made true by {' or '.join(labels)}; choose one with\n"
                        f"    goals:\n      - state: {token}\n        by: <one of: {', '.join(labels)}>"
                    )
                label = labels[0]
            claims = catalog.action_claims[label]
            base = overrides.get((scope_name, token)) or next((c for c in claims if c.token == token), None)
            if base is None:
                raise CompositionError(
                    f"{shown}{where}: {label} makes {token!r} as a side effect of another state; "
                    "put the relation on the state it makes first"
                )
            overrides[(scope_name, token)] = dataclasses.replace(
                base,
                scope=scope_name,
                requires=base.requires | frozenset(state_ref(r) for r in relation["after"]),
                invalidates=base.invalidates | frozenset(state_ref(r) for r in relation["breaks"]),
                origin=COMPOSITION_ORIGIN,
            )
