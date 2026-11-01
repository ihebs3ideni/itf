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
"""`itf contracts map|new|check`: discover, define and enforce contracts with the optional contract library.

    itf contracts map [--packs all|a,b] [--tests PATH...] [--format text|json|mermaid|html] [--output FILE]
    itf contracts new NAME --from-usage [--out FILE]
    itf contracts check --policy FILE [--targets T...] [--conformance]

The parts are those of the named packs (default: all) and of the project's own `conftest.py`; the tests are read
from `@itf.requires(...)` decorators without importing them; the definitions are those of the packs, of
`ITF_CONTRACTS_PATH` and of `--definitions DIR`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

from score.itf import contracts
from score.itf.contracts import inventory as inv
from score.itf.contracts import policy as policy_rules
from score.itf.contracts import render, run


def _packs(value: str) -> list[str]:
    return list(inv.known_packs()) if value == "all" else [p for p in value.split(",") if p]


def _sources(args) -> list:
    """The compositions named on the command line (`itf contracts map target.itf.yaml`), resolved."""
    from score.itf.cli import main as cli

    return [cli.find_target(t) for t in getattr(args, "target", None) or ()]


def _scope(args) -> tuple[list[str], list, list[str], dict]:
    """(packs, compositions, test paths, pack modules). Given compositions, the map covers exactly their packs
    (including those their `packs:` section locates), the project code beside them and the tests in their
    directories; otherwise every pack (or --packs) and --tests."""
    from score.itf.core.frontends import composition

    sources = _sources(args)
    if not sources:
        return _packs(args.packs), [], list(getattr(args, "tests", None) or ()), {}
    from score.itf.cli import main as cli

    overrides = cli.find_overrides(getattr(args, "override", None) or [])
    docs = [composition.load_all(s, overrides) for s in sources]
    names = {p for d in docs for p in composition.packs_of(d)}
    modules = {k: v for d in docs for k, v in composition.pack_modules(d).items()}
    tests = list(getattr(args, "tests", None) or ()) or sorted({str(Path(s.value).parent) for s in sources})
    return sorted(n for n in names if n != "project"), sources, tests, modules


def _pack_definition_dirs(modules: dict) -> list[str]:
    """A pack's definitions live in its own `contracts/` directory, also for packs a composition locates."""
    import importlib.util

    found = []
    for module in modules.values():
        spec = importlib.util.find_spec(module)
        if spec is not None and spec.origin:
            directory = Path(spec.origin).parent / "contracts"
            if directory.is_dir():
                found.append(str(directory))
    return found


def _conftests(sources) -> list:
    """The project code: the conftest beside each composition, else the project's own."""
    from score.itf.cli.main import load_conftest, project_conftest

    found = [m for m in (load_conftest(Path(s.value).parent / "conftest.py") for s in sources) if m is not None]
    if not found:
        conftest = project_conftest()
        found = [conftest] if conftest is not None else []
    return found


def _observed(args, packs, sources=(), tests=(), modules=None):
    """(catalog, errors, tests, definitions): what the commands read. Given compositions, only the definitions
    of the contracts they use are kept, so the map shows that target and nothing else."""
    catalog, errors = inv.load_catalog(packs, _conftests(sources), modules)
    requirements = inv.collect_requirements(tests)
    definitions = contracts.load_list([*(args.definitions or ()), *_pack_definition_dirs(modules or {})])
    if sources:
        used = set(contracts.contract_map(catalog, tests=requirements, definitions=[]))
        definitions = [d for d in definitions if d.contract in used]
    return catalog, errors, requirements, definitions


def _out(path: str) -> Path:
    """A relative output path is the user's: relative to where the command was run, also under `bazel run`."""
    from score.itf.cli.main import project_root

    return Path(path) if Path(path).is_absolute() else project_root() / path


def cmd_map(args) -> int:
    packs, sources, test_paths, modules = _scope(args)
    catalog, errors, tests, definitions = _observed(args, packs, sources, test_paths, modules)
    data = inv.inventory(catalog, definitions=definitions, tests=tests, errors=errors, packs=packs)
    text = render.render(data, args.format)
    if args.output:
        _out(args.output).write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
        print(f"wrote {args.output}")
    else:
        print(text)
    return 0


def cmd_reference(args) -> int:
    packs = _packs(args.packs)
    catalog, errors, _, definitions = _observed(args, packs)
    text = render.render_reference(inv.inventory(catalog, definitions=definitions, errors=errors, packs=packs))
    _out(args.output).write_text(text, encoding="utf-8")
    print(f"wrote {args.output}")
    return 1 if errors else 0


def cmd_new(args) -> int:
    if not args.from_usage:
        print("itf: `contracts new` builds a skeleton from usage: add --from-usage", file=sys.stderr)
        return 2
    packs, sources, test_paths, modules = _scope(args)
    catalog, errors, tests, definitions = _observed(args, packs, sources, test_paths, modules)
    mapped = contracts.contract_map(catalog, tests=tests, definitions=definitions)
    if args.name in mapped and mapped[args.name].definition is not None:
        print(
            f"itf: {args.name} is already defined in {mapped[args.name].definition.source}; edit that file",
            file=sys.stderr,
        )
        return 1
    try:
        skeleton = contracts.skeleton_from_usage(args.name, mapped)
    except KeyError as exc:
        print(f"itf: {exc.args[0]}", file=sys.stderr)
        return 1
    out = Path(args.out) if args.out else Path("contracts") / f"{args.name.replace('/', '_')}.yaml"
    if out.exists():
        print(f"itf: {out} exists; not overwriting it", file=sys.stderr)
        return 1
    out.parent.mkdir(parents=True, exist_ok=True)
    body = yaml.safe_dump({"contracts": [skeleton]}, sort_keys=False, default_flow_style=False)
    out.write_text(
        f"# Definition skeleton built from the shapes observed; fill in every TODO.\n{body}", encoding="utf-8"
    )
    print(f"wrote {out}")
    return 0


def cmd_check(args) -> int:
    from score.itf.cli import main as cli

    try:
        rules = policy_rules.load_policy(args.policy)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"itf: policy {args.policy}: {exc}", file=sys.stderr)
        return 2
    try:
        sources = [cli.find_target(t) for t in [*(args.target or ()), *(args.targets or ())]]
        overrides = cli.find_overrides(args.override)
    except (FileNotFoundError, ValueError) as exc:
        print(f"itf: {exc}", file=sys.stderr)
        return 2
    from score.itf.core.frontends import composition

    # The parts to check: the packs the given compositions name, else every pack.
    modules = {}
    if sources:
        docs = [composition.load_all(s, overrides) for s in sources]
        packs = sorted({p for d in docs for p in composition.packs_of(d)} - {"project"})
        modules = {k: v for d in docs for k, v in composition.pack_modules(d).items()}
    else:
        packs = _packs(args.packs)
    test_paths = list(args.tests or ()) or sorted({str(Path(s.value).parent) for s in sources})
    catalog, errors, tests, definitions = _observed(args, packs, sources, test_paths, modules)
    mapped = contracts.contract_map(catalog, tests=tests, definitions=definitions)
    plans = []
    violations = [contracts.Violation("load", e) for e in errors]
    for source in sources:
        session = cli.make_session(_Args(source, args), plan_only=True)
        failure = cli._resolve(session)
        if failure:
            violations.append(
                contracts.Violation("compile", f"{source.describe()} does not compile: {failure.strip()}")
            )
        else:
            plans.append((source.describe(), contracts.roles_of_plan(session._target_plan)))
    violations += contracts.check(rules, mapped, plans)
    if args.conformance or rules.get("conformance"):
        results = run.run_conformance(
            sources,
            {d.contract: d for d in definitions},
            [cli.project_conftest()] if cli.project_conftest() else [],
            overrides,
        )
        for r in results:
            print(
                f"[{r.status:^4}] {r.target}: {r.role} ({r.factory}) {r.contract}: {r.check}"
                + (f"  {r.detail}" if r.detail else "")
            )
            if r.status == "fail":
                violations.append(
                    contracts.Violation("conformance", f"{r.role} ({r.factory}) fails {r.check}: {r.detail}")
                )
        for line in run.not_run(catalog, {d.contract: d for d in definitions}, results):
            print(f"[ not run ] {line}")
    for v in violations:
        print(f"violation ({v.rule}): {v.message}", file=sys.stderr)
    print(f"{len(violations)} violation(s)")
    return 1 if violations else 0


class _Args:
    """What `make_session` reads from the command line, for a composition given by `check --targets`."""

    def __init__(self, source, args):
        self.target = source.value
        self.override = args.override
        self.run_dir = None


def add_contracts(sub) -> None:
    parser = sub.add_parser("contracts", help="map, define and check the contracts in use")
    commands = parser.add_subparsers(dest="contracts_command", required=True)

    def common(p, tests=True):
        p.add_argument("--packs", default="all", help="`all` (default) or a comma separated list of pack names")
        p.add_argument("--definitions", action="append", default=[], help="a directory of definitions (repeatable)")
        if tests:
            p.add_argument("--tests", nargs="+", default=[], metavar="PATH", help="test files or directories to read")

    p = commands.add_parser("map", help="every contract in use: offerers, needers, tests, definition, disagreements")
    p.add_argument("target", nargs="*", help="compositions to map (default: every pack, or --packs)")
    p.add_argument("--override", action="append", default=[], help="an override file for every target")
    common(p)
    p.add_argument("--format", choices=render.FORMATS, default="text")
    p.add_argument("--output", help="write here instead of standard output")
    p.set_defaults(func=cmd_map)

    p = commands.add_parser("reference", help="write the Markdown reference of the defined contracts")
    common(p, tests=False)
    p.add_argument("--output", required=True)
    p.set_defaults(func=cmd_reference)

    p = commands.add_parser("new", help="a definition skeleton for NAME, built from the shapes in use")
    p.add_argument("name")
    p.add_argument("target", nargs="*", help="compositions whose usage to read (default: every pack, or --packs)")
    p.add_argument("--from-usage", action="store_true", help="build it from the observed shapes (required)")
    p.add_argument("--out", help="the file to write (default: contracts/NAME.yaml); never overwritten")
    common(p)
    p.set_defaults(func=cmd_new)

    p = commands.add_parser("check", help="enforce a policy file; exit 1 on violations")
    p.add_argument("--policy", required=True, help="the policy: namespaces, roles, forbid_stability, conformance")
    p.add_argument("target", nargs="*", help="compositions whose roles the policy covers")
    p.add_argument("--targets", nargs="+", default=[], help="compositions whose roles the policy covers")
    p.add_argument("--override", action="append", default=[], help="an override file for every target")
    p.add_argument("--conformance", action="store_true", help="run the conformance checks against the targets")
    common(p)
    p.set_defaults(func=cmd_check)
