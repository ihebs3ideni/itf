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
"""`itf`: validate, plan, draw, bring up, take down and test a composition, and work with contracts.

A composition is a YAML or JSON document (the format `score.itf.core.frontends.composition` reads), given as an
argument or configured (`ITF_TARGET`, `itf_target` in pytest.ini, `[tool.itf] target` in pyproject.toml) exactly
as for a test run; override files (`--override`, `ITF_OVERRIDE`) are merged by role over it. Packs load from the
factory labels it names. `validate`, `plan` and `graph` read metadata only and construct nothing.
"""

from __future__ import annotations

import argparse
import code
import configparser
import importlib
import importlib.util
import json
import os
import re
import sys
import tempfile
import types
from pathlib import Path

from score.itf.cli.doctor import cmd_doctor
from score.itf.cli.graph import render_graph
from score.itf.core import TargetSource, TargetSourceError, resolve_overrides, resolve_target
from score.itf.core.adapters.definitions import definitions
from score.itf.core.engine.evidence import (
    HTML_NAME,
    render_summary,
    summarize,
    write_html,
)
from score.itf.core.engine.failure import banner
from score.itf.core.engine.labels import node_label
from score.itf.core.engine.scopes import display
from score.itf.core.session import ConfigValidationFailed, NotReady, ResolutionFailed, Session, TargetNameClash

PACKS_MODULE = "itf_cli_packs"


# ---------------------------------------------------------------- building a session from a composition


def project_root() -> Path:
    """Where the project's `pyproject.toml` is looked for: the directory the command was run from."""
    return Path(os.environ.get("BUILD_WORKING_DIRECTORY") or os.getcwd())  # `bazel run` starts in the runfiles


def _pytest_ini_option(root: Path, name: str):
    """`itf_target` from pytest.ini or `[tool.pytest.ini_options]`: the setting pytest itself reads, so the
    command line agrees with `pytest` about which composition a project uses."""
    parser = configparser.ConfigParser(interpolation=None)
    try:
        if parser.read(root / "pytest.ini", encoding="utf-8") and parser.has_option("pytest", name):
            return parser.get("pytest", name).strip(), f"pytest.ini {name}"
    except configparser.Error:
        return None
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        try:
            import tomllib

            options = tomllib.loads(pyproject.read_text(encoding="utf-8")).get("tool", {}).get("pytest", {})
        except (ImportError, ValueError):
            return None
        value = options.get("ini_options", {}).get(name)
        if isinstance(value, str) and value.strip():
            return value.strip(), f"pyproject.toml [tool.pytest.ini_options] {name}"
    return None


def find_target(target: str | None) -> TargetSource:
    """The composition to use: the argument, else `itf_target` (pytest.ini), ITF_TARGET, `[tool.itf] target`,
    as for a test run. Raises when none is configured or the value is not usable."""
    root = project_root()
    origin = "the command line"
    if not target:
        target, origin = _pytest_ini_option(root, "itf_target") or (None, origin)
    try:
        source = resolve_target(target, root=root, explicit_origin=origin)
    except TargetSourceError as exc:
        raise ValueError(str(exc)) from exc
    if source is None:
        raise FileNotFoundError(
            "no composition: pass one, or configure it (ITF_TARGET, `itf_target` in pytest.ini, "
            'or `[tool.itf] target = "target.itf.yaml"` in pyproject.toml)'
        )
    return source


def find_overrides(overrides) -> tuple[TargetSource, ...]:
    try:
        return resolve_overrides(overrides or (), root=project_root(), explicit_origin="--override")
    except TargetSourceError as exc:
        raise ValueError(str(exc)) from exc


def default_run_dir() -> Path:
    return project_root() / "itf-run"


_CONFTESTS: dict = {}


def load_conftest(path: Path) -> types.ModuleType | None:
    """A conftest.py loaded the way pytest loads it, once per file (its declarations register on import), or
    None when there is none."""
    if not path.is_file():
        return None
    key = path.resolve()
    if key not in _CONFTESTS:
        # A name of its own, so the `module:function` references its declarations publish resolve to this file
        # even when another module already answers to `conftest` (a test process has one).
        name = "conftest" if "conftest" not in sys.modules else f"conftest_{len(_CONFTESTS)}"
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        _CONFTESTS[key] = module
    return _CONFTESTS[key]


def project_conftest() -> types.ModuleType | None:
    """The project's conftest.py (current directory, else the project root): it holds the project's own
    capabilities and actions, so `itf` plans what a test run would."""
    for directory in dict.fromkeys((Path.cwd(), project_root())):
        module = load_conftest(directory / "conftest.py")
        if module is not None:
            return module
    return None


def target_conftest(source) -> types.ModuleType | None:
    """The conftest beside the composition (as pytest finds it for tests in that directory), else the
    project's."""
    value = Path(str(getattr(source, "value", "")))
    beside = load_conftest(value.parent / "conftest.py") if value.suffix in (".yaml", ".yml", ".json") else None
    return beside if beside is not None else project_conftest()


def make_session(args, **options) -> Session:
    source = find_target(args.target)
    roots = [m for m in (target_conftest(source),) if m is not None]
    return Session(
        roots=roots,
        target=source,
        overrides=find_overrides(getattr(args, "override", None)),
        run_dir=args.run_dir,
        definitions=definitions(),
        **options,
    )


# Errors that mean "this composition cannot be planned": reported, not a traceback.
_COMPOSITION_ERRORS = (ConfigValidationFailed, TargetNameClash, ValueError)


def _resolve(session: Session) -> str | None:
    """Resolve; returns the diagnostics to show on failure, else None."""
    try:
        session.resolve()
    except ResolutionFailed as exc:
        return banner(f"ITF: plan failed at gate {exc.gate}", 100) + "\n" + exc.rendered
    except _COMPOSITION_ERRORS as exc:
        return banner("ITF: composition rejected", 100) + "\n" + str(exc)
    except (ImportError, FileNotFoundError, TypeError, ValueError, KeyError) as exc:
        return banner("ITF: composition rejected", 100) + f"\n{type(exc).__name__}: {exc}"
    except Exception as exc:  # CrossContributorImport, WrongPhase, malformed document, ...
        return banner("ITF: composition rejected", 100) + f"\n{type(exc).__name__}: {exc}"
    return None


# ---------------------------------------------------------------- summaries


def target_summary(session: Session) -> str:
    plan = session._target_plan
    lines = [f"roles ({len(plan.nodes)}):"]
    lines += [f"  {node_label(display(n.ref), n.provider):<32} [{n.contract}]" for n in plan.nodes] or ["  -"]
    held = sorted(display(h) for h in session._last_observed)
    lines.append(f"held states ({len(held)}): {', '.join(held) or '-'}")
    return "\n".join(lines)


def _action_label(session: Session, step) -> str:
    """The label of the action that runs a step (`docker.start`), from its impl."""
    for label, desc in session._catalog.action_descs.items():
        if desc.impl == step.impl:
            return label
    return display(step.key)


def plan_summary(session: Session) -> str:
    lines = [target_summary(session).split("\nheld states")[0]]
    steps = session._action_plan.steps if session._action_plan is not None else ()
    lines.append(f"steps ({len(steps)}):")
    for i, step in enumerate(steps, 1):
        needs = f"  after {display(', '.join(step.requires))}" if step.requires else ""
        lines.append(f"  {i:>2}. {display(', '.join(step.delivers))} by {_action_label(session, step)}{needs}")
    return "\n".join(lines)


# ---------------------------------------------------------------- planning without constructing


def _planned(args, *, strict: bool = False):
    """(session, None) resolved in plan-only mode, or (None, exit code) after the problem was printed."""
    try:
        session = make_session(args, plan_only=True, strict_shapes=strict)
    except (FileNotFoundError, ValueError) as exc:
        print(f"itf: {exc}", file=sys.stderr)
        return None, 1
    failure = _resolve(session)
    if failure:
        print(failure, file=sys.stderr)
        return None, 1
    return session, None


def _in_scratch_dir(args):
    """A plan-only command writes nothing the user asked for: its run directory is a temporary one."""
    tmp = None
    if args.run_dir is None:
        tmp = tempfile.TemporaryDirectory(prefix="itf-plan-")
        args.run_dir = tmp.name
    return tmp


def definition_problems(session: Session) -> list[str]:
    """Disagreements between the parts this composition uses and their contract definitions (when the optional
    contract library is there): a definition's required member the factory does not publish, majors that do not
    match, a name defined twice. Metadata only."""
    try:
        from score.itf import contracts
    except ImportError:
        return []
    catalog = session._catalog
    labels = {n.provider for n in session._target_plan.nodes}
    parts = [catalog.factories[label] for label in sorted(labels)]
    steps = session._action_plan.steps if session._action_plan is not None else ()
    impls = {s.impl for s in steps}
    parts += [d for d in catalog.action_descs.values() if d.impl in impls]
    mapped = contracts.contract_map(parts, definitions=contracts.load_list())
    return [d.message for entry in mapped.values() for d in entry.disagreements if d.kind != "missing-member"]


def cmd_validate(args) -> int:
    tmp = _in_scratch_dir(args)
    try:
        session, failed = _planned(args, strict=True)
        if failed:
            return failed
        try:
            problems = definition_problems(session)
        except Exception as exc:  # noqa: BLE001 - a malformed definition file
            problems = [f"contract definitions cannot be read: {exc}"]
        for warning in session.warnings:
            print(f"warning: {warning}", file=sys.stderr)
        if problems:
            print(banner("ITF: composition rejected by its contract definitions", 100), file=sys.stderr)
            print("\n".join(f"  {p}" for p in problems), file=sys.stderr)
            return 1
        steps = len(session._action_plan.steps) if session._action_plan is not None else 0
        print(
            f"ok: {session.target_source.describe() if session.target_source else 'empty composition'}: "
            f"{len(session._target_plan.nodes)} roles, {steps} steps"
        )
        return 0
    finally:
        if tmp:
            tmp.cleanup()


def cmd_plan(args) -> int:
    tmp = _in_scratch_dir(args)
    try:
        session, failed = _planned(args)
        if failed:
            return failed
        plan_file = Path(args.run_dir) / "plan.json"
        if args.output:
            Path(args.output).write_text(plan_file.read_text(encoding="utf-8"), encoding="utf-8")
        print(plan_file.read_text(encoding="utf-8") if args.json else plan_summary(session))
        for warning in session.warnings:
            print(f"warning: {warning}", file=sys.stderr)
        if not tmp:
            print(f"plan written to {plan_file}", file=sys.stderr)
        return 0
    finally:
        if tmp:
            tmp.cleanup()


def cmd_graph(args) -> int:
    tmp = _in_scratch_dir(args)
    try:
        session, failed = _planned(args)
        if failed:
            return failed
        print(render_graph(session, args.kind, action_label=lambda step: _action_label(session, step)))
        return 0
    finally:
        if tmp:
            tmp.cleanup()


# ---------------------------------------------------------------- up, down, test


def undetachable(session: Session) -> str | None:
    """Why this target cannot be left running or taken down by a later process, or None when it can: every
    capability factory with a teardown must say (`observes`) that a factory built afresh sees what an earlier
    one created, so probes tell the truth and the teardown removes it."""
    catalog = session._catalog
    offenders = []
    for node in session._target_plan.nodes:
        factory = catalog.factories.get(node.provider)
        if factory is not None and factory.has_teardown and not factory.observable(dict(node.config)):
            offenders.append(f"{display(node.ref)} ({node.provider})")
    if not offenders:
        return None
    return (
        "this target cannot be left running or taken down by a later process: "
        f"{', '.join(offenders)} {'owns' if len(offenders) == 1 else 'own'} a teardown, and the factory does not "
        "say that a fresh instance observes "
        "what an earlier one created (`@capability(..., observes=True)`). Run `itf up` without --detach, "
        "which unwinds when you leave it."
    )


def cmd_up(args) -> int:
    args.run_dir = args.run_dir or default_run_dir()
    try:
        session = make_session(
            args, reuse="fresh" if args.fresh else "probe", on_exit="keep" if args.detach else "unwind"
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"itf: {exc}", file=sys.stderr)
        return 1
    status = 0
    try:
        failure = _resolve(session)
        if failure:
            print(failure, file=sys.stderr)
            return 1
        if args.detach:
            refusal = undetachable(session)
            if refusal:
                print(f"itf: --detach refused: {refusal}", file=sys.stderr)
                return 1
        try:
            session.bring_up()
        except NotReady as exc:
            print(exc.failure.render() if exc.failure is not None else f"ITF: not ready: {exc}", file=sys.stderr)
            status = 1
            return status
        print(target_summary(session))
        print(f"\nrun directory: {session.run_dir}")
        if args.detach:
            print("detached: the target keeps running; `itf down` takes it down")
        elif sys.stdin.isatty():
            code.interact(
                banner="itf: `target` and `session` are in scope; leave the console (Ctrl-D) to tear everything down.",
                local={"target": session.target, "session": session},
                exitmsg="itf: unwinding ...",
            )
    except KeyboardInterrupt:
        print("\nitf: interrupted, unwinding ...", file=sys.stderr)
        status = 130
    finally:
        try:
            session.close()
        except KeyboardInterrupt:  # a second Ctrl-C while unwinding: finish the unwind anyway
            session.close()
        problems = session.close_problems()
        if problems is not None:
            print(problems.render(), file=sys.stderr)
            status = status or 1
        evidence = Path(session.run_dir) / HTML_NAME
        if evidence.is_file():
            print(f"evidence: {evidence}")
    return status


def cmd_down(args) -> int:
    """A fresh session: its probes observe what holds, and the unwind removes what they observed (D-16)."""
    args.run_dir = args.run_dir or default_run_dir()
    try:
        session = make_session(args, reuse="probe", on_exit="unwind")
    except (FileNotFoundError, ValueError) as exc:
        print(f"itf: {exc}", file=sys.stderr)
        return 1
    failure = _resolve(session)
    if failure:
        print(failure, file=sys.stderr)
        return 1
    refusal = undetachable(session)
    if refusal:
        print(f"itf: down refused: {refusal}", file=sys.stderr)
        return 1
    held = sorted(display(h) for h in session._last_observed)
    session.close()
    report = session._unwind_report
    print(f"observed ({len(held)}): {', '.join(held) or '-'}")
    dismantled = [display(ref) for ref in (report.dismantled if report else ())]
    print(f"dismantled ({len(dismantled)}): {', '.join(dismantled) or '-'}")
    if not held:
        print("nothing held: the target was not up")
    problems = session.close_problems()
    if problems is not None:
        print(problems.render(), file=sys.stderr)
        return 1
    return 0


def _adapter_is_installed() -> bool:
    """A pip install registers the adapter as a pytest11 entry point; then `-p` would load it twice."""
    from importlib import metadata

    return any(ep.value.split(":")[0] == ADAPTER for ep in metadata.entry_points(group="pytest11"))


ADAPTER = "score.itf.core.adapters.pytest.plugin"


def cmd_test(args) -> int:
    """pytest with the composition configured: what `pytest` does with `--itf-target`, from the command line."""
    import pytest

    try:
        source = find_target(args.target)
        overrides = find_overrides(args.override)
    except (FileNotFoundError, ValueError) as exc:
        print(f"itf: {exc}", file=sys.stderr)
        return 1
    os.environ["ITF_TARGET"] = source.value
    if overrides:
        os.environ["ITF_OVERRIDE"] = os.pathsep.join(o.value for o in overrides)
    plugin = [] if _adapter_is_installed() else ["-p", ADAPTER]
    return int(pytest.main([*plugin, *args.pytest_args]))


# ---------------------------------------------------------------- diff


def _read_plan(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _nodes(plan: dict) -> dict:
    target = plan.get("target") or {}
    nodes = list(target.get("nodes", ()))
    for scope in (target.get("scopes") or {}).values():
        nodes += scope.get("nodes", ())
    return {f"{n['scope']}.{n['name']}": n for n in nodes}


def _steps(plan: dict) -> list:
    action = plan.get("action") or {}
    return list(action.get("steps", ()))


def _step_key(step: dict) -> str:
    return step.get("key") or f"{step.get('impl')}:{','.join(step.get('delivers', ()))}"


def _field_changes(old: dict, new: dict, prefix: str = "") -> list[str]:
    out = []
    for key in sorted(set(old) | set(new)):
        a, b = old.get(key), new.get(key)
        if a == b:
            continue
        if isinstance(a, dict) and isinstance(b, dict):
            out += _field_changes(a, b, f"{prefix}{key}.")
        else:
            out.append(f"{prefix}{key}: {json.dumps(a, sort_keys=True)} -> {json.dumps(b, sort_keys=True)}")
    return out


def diff_plans(old: dict, new: dict) -> list[str]:
    lines: list[str] = []
    a, b = _nodes(old), _nodes(new)
    lines += [f"+ node {ref}  ({b[ref]['provider']})" for ref in b if ref not in a]
    lines += [f"- node {ref}  ({a[ref]['provider']})" for ref in a if ref not in b]
    for ref in a:
        if ref in b and a[ref] != b[ref]:
            lines.append(f"~ node {ref}")
            lines += [f"      {change}" for change in _field_changes(a[ref], b[ref])]
    sa, sb = {_step_key(s): s for s in _steps(old)}, {_step_key(s): s for s in _steps(new)}
    lines += [f"+ step {key}" for key in sb if key not in sa]
    lines += [f"- step {key}" for key in sa if key not in sb]
    for key in sa:
        if key in sb and sa[key] != sb[key]:
            lines.append(f"~ step {key}")
            lines += [f"      {change}" for change in _field_changes(sa[key], sb[key])]
    common_old = [k for k in sa if k in sb]
    common_new = [k for k in sb if k in sa]
    if common_old != common_new:
        lines.append("~ steps reordered:")
        lines.append(f"      was {' -> '.join(common_old)}")
        lines.append(f"      now {' -> '.join(common_new)}")
    for key in ("assumptions",):
        if old.get(key) != new.get(key):
            lines.append(f"~ {key} changed")
    return lines


def cmd_diff(args) -> int:
    try:
        old, new = _read_plan(args.old), _read_plan(args.new)
    except (OSError, ValueError) as exc:
        print(f"itf: {exc}", file=sys.stderr)
        return 2
    lines = diff_plans(old, new)
    print("\n".join(lines) if lines else "plans are identical")
    return 1 if lines else 0


# ---------------------------------------------------------------- evidence


def cmd_evidence(args) -> int:
    try:
        if args.summary:
            print(render_summary(summarize(args.run_dirs)))
            return 0
        if len(args.run_dirs) != 1:
            print("itf evidence: give exactly one run directory (or --summary for several)", file=sys.stderr)
            return 2
        print(write_html(args.run_dirs[0]))
        return 0
    except FileNotFoundError as exc:
        print(f"itf: {exc}", file=sys.stderr)
        return 1


# ---------------------------------------------------------------- argument parsing


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="itf", description="Integration Test Framework: work with a composition.")
    sub = parser.add_subparsers(dest="command", required=True)

    def target_args(p, positional=True):
        if positional:
            p.add_argument(
                "target",
                nargs="?",
                help="a YAML or JSON composition (default: the configured one: ITF_TARGET, itf_target, [tool.itf])",
            )
        else:
            p.add_argument("--target", help="the composition (default: the configured one)")
        p.add_argument(
            "--override",
            action="append",
            default=[],
            help="an override file merged by role over the target (repeatable; default: ITF_OVERRIDE)",
        )
        p.add_argument("--run-dir", default=None, help="where run artifacts go")

    p = sub.add_parser("validate", help="compile the composition (every metadata check); exit 1 with diagnostics")
    target_args(p)
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("plan", help="resolve only and print the plan; exit 1 with diagnostics")
    target_args(p)
    p.add_argument("--json", action="store_true", help="print plan.json instead of the summary")
    p.add_argument("--output", help="also write plan.json here")
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("graph", help="draw the topology and the bring-up sequence from metadata, as Mermaid")
    target_args(p)
    p.add_argument("--kind", choices=("topology", "sequence", "both"), default="both")
    p.add_argument("--format", choices=("mermaid",), default="mermaid")
    p.set_defaults(func=cmd_graph)

    p = sub.add_parser("up", help="bring a composition up, print the target and open a console on it")
    target_args(p)
    p.add_argument("--fresh", action="store_true", help="run every planned action, ignoring what probes observe")
    p.add_argument("--detach", action="store_true", help="leave it running and exit; `itf down` takes it down")
    p.set_defaults(func=cmd_up)

    p = sub.add_parser("down", help="take down what probes observe (a fresh session; for observing factories only)")
    target_args(p)
    p.set_defaults(func=cmd_down)

    p = sub.add_parser("test", help="run pytest with the composition configured: itf test [options] [pytest args]")
    target_args(p, positional=False)
    p.set_defaults(func=cmd_test, pytest_args=[])

    p = sub.add_parser("doctor", help="check the host prerequisites of the packs a composition names")
    target_args(p)
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("diff", help="compare two plan.json files; exit 0 if identical, 1 otherwise")
    p.add_argument("old")
    p.add_argument("new")
    p.set_defaults(func=cmd_diff)

    p = sub.add_parser("evidence", help="write evidence.html for a run, or summarize several runs")
    p.add_argument("run_dirs", nargs="+", metavar="run-dir")
    p.add_argument("--summary", action="store_true", help="aggregate several runs instead")
    p.set_defaults(func=cmd_evidence)

    from score.itf.cli.contracts_cmd import add_contracts

    add_contracts(sub)
    return parser


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    if argv and argv[0] == "test" and not {"-h", "--help"} & set(argv[1:2]):
        # Everything `itf test` does not know is pytest's: options keep their order with their values.
        args, rest = parser.parse_known_args(["test"] + _own_options(argv[1:]))
        args.pytest_args = _pytest_rest(argv[1:])
        return args.func(args)
    args = parser.parse_args(argv)
    return args.func(args)


_OWN = ("--target", "--override", "--run-dir")


def _own_options(argv: list[str]) -> list[str]:
    """The leading `--target X`, `--override X`, `--run-dir X` of `itf test`; the rest belongs to pytest."""
    found, i = [], 0
    while i < len(argv) and argv[i] in _OWN and i + 1 < len(argv):
        found += argv[i : i + 2]
        i += 2
    return found


def _pytest_rest(argv: list[str]) -> list[str]:
    return argv[len(_own_options(argv)) :]


if __name__ == "__main__":
    sys.exit(main())
