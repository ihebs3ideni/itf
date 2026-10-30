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
"""A YAML frontend for `itf_setup`/`itf_init`: translates a document into the exact `ctx` calls a
Python recipe would make. Not a parallel input path — `SetupContext`/`InitContext` are the only
boundary a contributor crosses, YAML or Python (D-31).

A YAML document can only *select and wire* what packs already published (`using=` names an existing
provider or action). It can declare new capability contract tokens and nodes, goals, relations and
assumptions — the same things a policy declares — but never a new provider or action: those are
Python code because they *do* things, and nothing here ever imports a pack.

`extends:` composes documents before translation, not at claim time (docs/octo-kit/30-decisions.md
D-31): ancestors are resolved first, merged into one effective document, and only that document is
translated into `ctx` calls. OCTO never sees "this came from a parent file" — by the time a claim
exists, inheritance has already happened, the same way it would if you had copy-pasted the merged
YAML by hand. Precedence between *contributors* (a YAML pack vs. the root conftest) is untouched:
it is still decided by `origin`, exactly as it is for two Python modules.

Schema (every section optional). Top-level `nodes`/`aliases`/`rebinds`/`goals`/`relations`/
`assumptions` address the target's root scope (`ctx.add(...)`, `ctx.goal(...)`); the same keys under
`scopes.<name>` address a device scope. Nothing applies to every scope.

    extends:                              # relative to this file; ancestors first, this file last
      - other.yaml
    setup:
      contracts:
        - token: <token>
          gives: <members>
          needs: <slots>
      nodes:
        - name: <name>
          contract: <token>
          using: <provider>
          bind:
            <slot>: <node name>
          config:
            <key>: <scalar>
      aliases:                            # target: ".name" (root) or "scope.name"
        - name: <name>
          target: <target>
      rebinds:
        - name: <name>
          slots:
            <slot>: <node name>
      scopes:
        <scope>:
          nodes:                          # as above
          aliases:
          rebinds:
    init:
      states:                             # ctx.state(...): which action delivers a token, everywhere
        - token: <token>
          using: <action>
      goals:
        - <state>
      relations:
        - state: <state>
          requires:
            - <state>
          invalidates:
            - <state>
      assumptions:
        - token: <token>
          owner: <who>
          reason: <why>
      scopes:
        <scope>:
          goals:
          relations:
          assumptions:

Node `config` values may reference the environment: `${NAME}`, or `${NAME:-default}` when unset
(`$${` is a literal `${`). That is how a build system hands a recipe a built artifact's path, and how
a secret reaches a node without being written into the document. A value that is exactly one
reference is read as a YAML scalar, so `port: ${SSH_PORT:-22}` is an int; an unset name without a
default is an error naming the node.

Merge rules, applied recursively: dicts merge key by key. `nodes`, `contracts`, `aliases`, `rebinds`,
`assumptions` and `states` merge their list entries by name/token (a derived layer can override one
field of one entry without restating its siblings). `goals` and `relations` are additive — concatenated
across layers — because OCTO already treats repeated goals and relations as a union (no entry here is
ever "lost" by appearing in two layers). Anything else — scalars, and any list with no merge rule — is
replaced wholesale by the more-derived layer.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Mapping

import yaml

_IDENTITY_KEY = {
    "contracts": "token",
    "nodes": "name",
    "aliases": "name",
    "rebinds": "name",
    "assumptions": "token",
    "states": "token",
}
_ADDITIVE_LISTS = {"goals", "relations"}


def _read(source: Any) -> tuple[Mapping[str, Any], Path | None]:
    """Normalise `source` into (document, path-or-None).

    Accepts an already-parsed mapping (a direct API call), a filesystem path, or inline YAML/JSON
    text — so a CLI flag's path, an env var's path, and a hand-built dict all reach the same
    translation code (D-31). A relative path with no parent recorded is resolved against the
    current working directory, same as `open()`.
    """
    if isinstance(source, Mapping):
        return source, None
    try:
        candidate = Path(source)
        path = candidate if candidate.is_file() else None
    except OSError:
        path = None  # e.g. "File name too long": multiline text can't even be stat()'d as a path
    if path is not None:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}, path.resolve()
    return yaml.safe_load(str(source)) or {}, None


def _merge_mapping(base: Mapping, overlay: Mapping) -> dict:
    out = dict(base)
    for key, value in overlay.items():
        out[key] = _merge_value(key, base.get(key), value) if key in base else value
    return out


def _merge_value(key: str, base: Any, overlay: Any) -> Any:
    if isinstance(base, Mapping) and isinstance(overlay, Mapping):
        return _merge_mapping(base, overlay)
    if isinstance(base, list) and isinstance(overlay, list):
        if key in _IDENTITY_KEY:
            return _merge_by_identity(base, overlay, _IDENTITY_KEY[key])
        if key in _ADDITIVE_LISTS:
            return _union_list(base, overlay)
    return overlay


def _merge_by_identity(base: list, overlay: list, key: str) -> list:
    by_key = {item[key]: item for item in base}
    order = [item[key] for item in base]
    for item in overlay:
        k = item[key]
        if k in by_key:
            by_key[k] = _merge_mapping(by_key[k], item)
        else:
            by_key[k] = item
            order.append(k)
    return [by_key[k] for k in order]


def _union_list(base: list, overlay: list) -> list:
    out = list(base)
    for item in overlay:
        if item not in out:
            out.append(item)
    return out


def resolve_document(source: Any, *, _seen: frozenset = frozenset()) -> dict:
    """Follow `extends`, merge ancestors-first, return one effective document."""
    doc, path = _read(source)
    if path is not None:
        if path in _seen:
            raise ValueError(f"itf yaml frontend: extends cycle at {path}")
        _seen = _seen | {path}

    effective: dict = {}
    for parent in doc.get("extends", ()):
        parent_source = (path.parent / parent) if path is not None else parent
        if path is not None and not Path(parent_source).exists() and Path(parent).is_file():
            parent_source = Path(parent)  # a generated parent, named by its path from the working directory
        effective = _merge_mapping(effective, resolve_document(parent_source, _seen=_seen))
    return _merge_mapping(effective, {k: v for k, v in doc.items() if k != "extends"})


_ENV_REF = re.compile(r"\$(\$)?\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


def _expand(value: Any, where: str) -> Any:
    """Substitute `${NAME}` / `${NAME:-default}` in a config string; see the module docstring."""
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
        raise ValueError(f"itf yaml frontend: {where} references ${{{name}}}, which is not set")

    whole = _ENV_REF.fullmatch(value)
    expanded = _ENV_REF.sub(substitute, value)
    if whole and not whole.group(1):
        return yaml.safe_load(expanded) if expanded else expanded
    return expanded


def _config(node: Mapping, scope_label: str) -> Mapping | None:
    config = node.get("config")
    if not config:
        return config
    where = f"node {scope_label}{node['name']}"
    return {key: _expand(value, f"{where} config {key!r}") for key, value in config.items()}


def _translate_setup(ctx, doc: Mapping) -> None:
    setup = doc.get("setup") or {}
    for contract in setup.get("contracts", ()):
        ctx.contract(contract["token"], gives=contract.get("gives"), needs=contract.get("needs"))
    _translate_setup_scope(ctx, setup, "")
    for scope_name, scope_doc in (setup.get("scopes") or {}).items():
        _translate_setup_scope(ctx.scope(scope_name), scope_doc, f"{scope_name}.")


def _translate_setup_scope(scope, scope_doc: Mapping, label: str) -> None:
    for node in scope_doc.get("nodes", ()):
        scope.add(
            node["name"],
            node.get("contract"),
            using=node.get("using"),
            bind=node.get("bind"),
            config=_config(node, label),
        )
    for alias in scope_doc.get("aliases", ()):
        scope.alias(alias["name"], alias["target"])
    for rebind in scope_doc.get("rebinds", ()):
        scope.rebind(rebind["name"], **(rebind.get("slots") or {}))


def _translate_init(ctx, doc: Mapping) -> None:
    init = doc.get("init") or {}
    for state in init.get("states", ()):
        ctx.state(state["token"], using=state["using"])
    _translate_init_scope(ctx, init)
    for scope_name, scope_doc in (init.get("scopes") or {}).items():
        _translate_init_scope(ctx.scope(scope_name), scope_doc)


def _translate_init_scope(scope, scope_doc: Mapping) -> None:
    goals = scope_doc.get("goals", ())
    if goals:
        scope.goal(*goals)
    for relation in scope_doc.get("relations", ()):
        scope.relate(
            relation["state"], requires=relation.get("requires", ()), invalidates=relation.get("invalidates", ())
        )
    for assumption in scope_doc.get("assumptions", ()):
        scope.assume(assumption["token"], owner=assumption.get("owner", ""), reason=assumption.get("reason", ""))


def recipe_document() -> str:
    """The recipe document a build system generated for this run (`ITF_RECIPE_DOCUMENT`), for a
    conftest that loads it explicitly: `load_setup(ctx, recipe_document())`."""
    path = os.environ.get("ITF_RECIPE_DOCUMENT")
    if not path:
        raise RuntimeError("ITF_RECIPE_DOCUMENT is not set: give the test a recipe (py_itf_test(recipe = ...))")
    return path


def load_setup(ctx, source: Any) -> None:
    """Resolve `extends`, then issue the same `ctx` calls a Python `itf_setup` would."""
    _translate_setup(ctx, resolve_document(source))


def load_init(ctx, source: Any) -> None:
    """Resolve `extends`, then issue the same `ctx` calls a Python `itf_init` would."""
    _translate_init(ctx, resolve_document(source))
