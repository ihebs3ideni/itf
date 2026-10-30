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
"""Build the pack catalog: catalog.html for people, catalog.db (SQLite) for agents and scripts.

Data comes from the same decorators ITF publishes at runtime, so the catalog cannot drift from the
code. Run from the repository root: `.venv/bin/python tools/catalog/build_catalog.py [--db]`.
"""

from __future__ import annotations

import argparse
import os
import tempfile
import ast
import dataclasses
import hashlib
import importlib
import inspect
import json
import sqlite3
import sys
import typing
from pathlib import Path

ROOT = Path(__file__).absolute().parents[2]
PACKS = ROOT / "score" / "itf" / "packs"
PREFIX = "score.itf.packs."
TEMPLATE = Path(__file__).with_name("template.html")
SCHEMA = Path(__file__).with_name("schema.sql")
DB = Path(tempfile.gettempdir()) / "itf-catalog.db"
PLACEHOLDER = "/*__CATALOG_DATA__*/null"


from score.itf.core.engine.publish import _STAGING, ActionDescriptor, ProviderDescriptor  # noqa: E402
from score.itf.core.engine.realize import default_resolver  # noqa: E402

VARIANTS = ("real", "sim", "generic", "legacy", "windows", "multicast", "host")


def _doc(obj) -> str:
    return inspect.cleandoc(obj.__doc__) if getattr(obj, "__doc__", None) else ""


def _members(shape) -> list[str]:
    return sorted(member.name for member in shape.members)


def _pack(module: str) -> str:
    """score.itf.packs.ssh.sim.providers -> ssh"""
    return module[len(PREFIX) :].split(".", 1)[0]


def _variant(module: str) -> str:
    parts = module[len(PREFIX) :].split(".")
    return parts[1] if len(parts) > 2 and parts[1] in VARIANTS else "shared"


def _state_token(ref: str) -> str:
    return ref.split(":", 1)[1] if ":" in ref else ref


def _entrypoints() -> list[str]:
    """Every pack module that lists `pytest_plugins` at top level: what a recipe or a py_itf_plugin loads."""
    names = []
    for path in sorted(PACKS.glob("*/**/*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if any(
            isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "pytest_plugins" for t in n.targets)
            for n in tree.body
        ):
            names.append(PREFIX + ".".join(path.relative_to(PACKS).with_suffix("").parts))
    return names


def _load(entrypoint: str, seen: set[str]) -> list[str]:
    """Import an entrypoint the way pytest would, following `pytest_plugins`; return every module."""
    if entrypoint in seen:
        return []
    seen.add(entrypoint)
    module = importlib.import_module(entrypoint)
    plugins = getattr(module, "pytest_plugins", ())
    loaded = [entrypoint]
    for name in [plugins] if isinstance(plugins, str) else plugins:
        loaded += _load(name, seen)
    return loaded


def _config(schema) -> list[dict]:
    rows = []
    for field in schema.fields if schema else ():
        default = None if field.required or field.default is dataclasses.MISSING else field.default
        rows.append(
            {
                "name": field.name,
                "type": field.type_name,
                "required": field.required,
                "sensitive": field.sensitive,
                "default": None if field.sensitive else default,
            }
        )
    return rows


def _needs(needs) -> list[dict]:
    return [{"slot": need.slot, "contract": need.contract, "members": _members(need.expected)} for need in needs]


def _returned_class(func):
    """The object type a provider factory hands to tests, unwrapping `Iterator[X]`."""
    try:
        hint = inspect.signature(func, eval_str=True).return_annotation
    except (NameError, TypeError, ValueError):
        return None
    args = typing.get_args(hint)
    if typing.get_origin(hint) is not None and args:
        hint = args[0]
    return hint if inspect.isclass(hint) else None


def _api(cls, names: list[str]) -> list[dict]:
    """Signature and first doc paragraph of each published member, read from the class."""
    rows = []
    annotations = {}
    for klass in reversed(cls.__mro__ if cls else ()):
        annotations.update(getattr(klass, "__annotations__", {}))
    for name in names:
        attr = inspect.getattr_static(cls, name, None) if cls else None
        signature, doc = "", ""
        if isinstance(attr, property):
            signature, doc = "(property)", _doc(attr.fget)
        elif callable(attr) or isinstance(attr, (staticmethod, classmethod)):
            func = getattr(cls, name)
            try:
                signature = str(inspect.signature(func)).replace("(self, ", "(").replace("(self)", "()")
                signature = signature.replace("'", "")
            except (TypeError, ValueError):
                pass
            doc = _doc(func)
        elif name in annotations:
            hint = annotations[name]
            signature = f": {hint if isinstance(hint, str) else getattr(hint, '__name__', hint)}"
        rows.append({"member": name, "signature": signature, "doc": doc.split("\n\n", 1)[0]})
    return rows


def build() -> dict:
    entrypoints, errors = [], []
    for name in _entrypoints():
        try:
            modules = _load(name, set())
        except Exception as exc:  # a missing optional dependency must not hide the other packs
            errors.append({"entrypoint": name, "error": f"{type(exc).__name__}: {exc}"})
            continue
        entrypoints.append(
            {
                "name": name,
                "pack": _pack(name),
                "doc": _doc(sys.modules[name]),
                "modules": sorted(set(modules) - {name}),
            }
        )

    providers, actions = [], []
    for module_name in sorted(_STAGING):
        if not module_name.startswith(PREFIX):
            continue
        loaded_by = [e["name"] for e in entrypoints if module_name in e["modules"]]
        for desc in _STAGING[module_name]:
            common = {
                "pack": _pack(module_name),
                "module": module_name,
                "variant": _variant(module_name),
                "entrypoints": loaded_by,
                "doc": _doc(default_resolver(desc.impl)),
            }
            if isinstance(desc, ProviderDescriptor):
                gives = _members(desc.gives)
                providers.append(
                    {
                        **common,
                        "name": desc.name,
                        "contract": desc.implements,
                        "gives": gives,
                        "api": _api(_returned_class(default_resolver(desc.impl)), gives),
                        "needs": _needs(desc.needs),
                        "config": _config(desc.config_schema),
                    }
                )
            elif isinstance(desc, ActionDescriptor):
                actions.append(
                    {
                        **common,
                        "name": desc.name,
                        "state": desc.token,
                        "also": sorted(desc.also_delivers),
                        "probe": bool(desc.probe),
                        "requires": sorted(desc.requires),
                        "invalidates": sorted(desc.invalidates),
                        "uses": _needs(desc.uses),
                    }
                )

    packs = []
    for directory in sorted(d for d in PACKS.iterdir() if (d / "__init__.py").exists()):
        readme = directory / "README.md"
        package = importlib.import_module(PREFIX + directory.name)
        packs.append(
            {
                "name": directory.name,
                "doc": _doc(package),
                "readme": readme.read_text(encoding="utf-8") if readme.exists() else "",
                "requirements": sorted(p.name for p in directory.glob("requirement*.txt")),
                "entrypoints": [e["name"] for e in entrypoints if e["pack"] == directory.name],
            }
        )

    capabilities = sorted(
        {p["contract"] for p in providers}
        | {n["contract"] for item in providers + actions for n in item["needs" if "needs" in item else "uses"]}
    )
    states = sorted(
        {a["state"] for a in actions}
        | {s for a in actions for s in a["also"]}
        | {_state_token(r) for a in actions for r in a["requires"] + a["invalidates"]}
    )
    return {
        "packs": packs,
        "entrypoints": entrypoints,
        "providers": providers,
        "actions": actions,
        "capabilities": capabilities,
        "states": states,
        "errors": errors,
    }


def render(data: dict) -> str:
    payload = json.dumps(data, indent=None, sort_keys=True, default=str).replace("</", "<\\/")
    return TEMPLATE.read_text(encoding="utf-8").replace(PLACEHOLDER, payload)


def source_hash() -> str:
    """Fingerprint of everything the catalog is built from; a stored DB with another hash is stale."""
    digest = hashlib.sha256()
    files = [Path(__file__), SCHEMA, *PACKS.glob("*/**/*.py"), *PACKS.glob("*/**/*.md")]
    for path in sorted(p for p in files if "__pycache__" not in p.parts):
        digest.update(str(path.relative_to(ROOT)).encode() + b"\0" + path.read_bytes())
    return digest.hexdigest()


def _area(token: str) -> str:
    parts = token.split(".")
    return parts[2] if len(parts) > 3 else ""


SEARCH_FILL = """
INSERT INTO search SELECT 'capability', c.token, c.token,
  (SELECT group_concat(p.name || ' ' || p.doc || ' ' ||
     (SELECT group_concat(m.member || ' ' || m.doc, ' ') FROM provider_members m
      WHERE m.provider = p.name AND m.module = p.module), ' ')
   FROM providers p WHERE p.contract = c.token) FROM capabilities c;
INSERT INTO search SELECT 'state', s.token, s.token,
  (SELECT group_concat(a.name || ' ' || a.doc, ' ') FROM actions a
   WHERE a.state = s.token OR EXISTS (SELECT 1 FROM action_relations r WHERE r.action = a.name
     AND r.module = a.module AND r.kind = 'also' AND r.state = s.token)) FROM states s;
INSERT INTO search SELECT 'provider', p.name, p.contract,
  p.doc || ' ' || (SELECT ifnull(group_concat(m.member || ' ' || m.doc, ' '), '') FROM provider_members m
                   WHERE m.provider = p.name AND m.module = p.module)
        || ' ' || (SELECT ifnull(group_concat(c.field, ' '), '') FROM provider_config c
                   WHERE c.provider = p.name AND c.module = p.module) FROM providers p;
INSERT INTO search SELECT 'member', m.provider || '.' || m.member, m.member || m.signature, m.doc
  FROM provider_members m;
INSERT INTO search SELECT 'action', a.name, a.state, a.doc FROM actions a;
INSERT INTO search SELECT 'pack', k.name, k.doc, k.readme FROM packs k;
"""


def write_db(data: dict, path: Path, fingerprint: str = "") -> None:
    """Write the catalog as SQLite; the schema (with its comments) is tools/catalog/schema.sql."""
    tmp = path.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    db = sqlite3.connect(tmp)
    db.executescript(SCHEMA.read_text(encoding="utf-8"))
    ins = lambda table, *rows: (
        db.executemany(  # noqa: E731
            f"INSERT INTO {table} VALUES ({','.join('?' * len(rows[0]))})", rows
        )
        if rows
        else None
    )

    ins("packs", *[(p["name"], p["doc"], p["readme"], ",".join(p["requirements"])) for p in data["packs"]])
    ins("entrypoints", *[(e["name"], e["pack"], e["doc"]) for e in data["entrypoints"]])
    ins("entrypoint_modules", *[(e["name"], m) for e in data["entrypoints"] for m in [e["name"], *e["modules"]]])
    ins("capabilities", *[(t, _area(t)) for t in data["capabilities"]])
    ins("states", *[(t, _area(t)) for t in data["states"]])
    for p in data["providers"]:
        key = (p["name"], p["module"])
        ins("providers", (*key, p["contract"], p["pack"], p["variant"], p["doc"]))
        ins("provider_members", *[(*key, m["member"], m["signature"], m["doc"]) for m in p["api"]])
        ins("provider_needs", *[(*key, n["slot"], n["contract"], ",".join(n["members"])) for n in p["needs"]])
        ins(
            "provider_config",
            *[
                (
                    *key,
                    c["name"],
                    c["type"],
                    int(c["required"]),
                    int(c["sensitive"]),
                    None if c["required"] or c["sensitive"] else json.dumps(c["default"], default=str),
                )
                for c in p["config"]
            ],
        )
    for a in data["actions"]:
        key = (a["name"], a["module"])
        ins("actions", (*key, a["state"], a["pack"], a["variant"], int(a["probe"]), a["doc"]))
        relations = (
            [("also", r) for r in a["also"]]
            + [("requires", r) for r in a["requires"]]
            + [("invalidates", r) for r in a["invalidates"]]
        )
        ins(
            "action_relations",
            *[
                (*key, kind, ref, ref.split(":", 1)[0] if ":" in ref else None, _state_token(ref))
                for kind, ref in relations
            ],
        )
        ins("action_uses", *[(*key, u["slot"], u["contract"], ",".join(u["members"])) for u in a["uses"]])
    ins("load_errors", *[(e["entrypoint"], e["error"]) for e in data["errors"]])
    ins(
        "meta",
        ("source_hash", fingerprint),
        ("counts", json.dumps({k: len(data[k]) for k in ("packs", "capabilities", "states", "providers", "actions")})),
    )
    db.executescript(SEARCH_FILL)
    db.commit()
    db.close()
    tmp.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("catalog.html"),
        help="relative paths resolve against the workspace under `bazel run`",
    )
    parser.add_argument("--db", type=Path, nargs="?", const=DB, help=f"also write SQLite (default {DB})")
    args = parser.parse_args()
    workspace = Path(os.environ.get("BUILD_WORKSPACE_DIRECTORY", "."))
    args.out = workspace / args.out
    if args.db:
        args.db = workspace / args.db
    data = build()
    args.out.write_text(render(data), encoding="utf-8")
    if args.db:
        write_db(data, args.db, source_hash())
    print(
        f"{args.out}: {len(data['packs'])} packs, {len(data['capabilities'])} capabilities, "
        f"{len(data['states'])} states, {len(data['providers'])} providers, {len(data['actions'])} actions"
    )
    for error in data["errors"]:
        print(f"skipped {error['entrypoint']}: {error['error']}", file=sys.stderr)


if __name__ == "__main__":
    main()
