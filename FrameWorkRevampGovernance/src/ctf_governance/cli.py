"""``ctf-catalog`` -- dump the composed ecosystem catalog and governance findings.

Each positional argument is an importable module that registers CTF hookimpls
(``pytest_ctf_setup`` / ``pytest_ctf_steps``). The modules are inspected in
isolation (no pytest session), a cross-plugin catalog is built, and the result
is printed as text or JSON.

Exit codes:
    0  no error-severity findings (warnings allowed)
    1  error-severity findings present, or --strict with any finding
    2  a plugin module could not be imported
"""

from __future__ import annotations

import argparse
import dataclasses
import importlib
import json
import os
import sys
from typing import Sequence

from ctf_governance.catalog import Catalog, build_catalog
from ctf_governance.collector import inspect_plugin
from ctf_governance.naming import DEFAULT_POLICY, NamespacePolicy


def _load(module_path: str) -> object:
    return importlib.import_module(module_path)


def _policy(args: argparse.Namespace) -> NamespacePolicy:
    policy = DEFAULT_POLICY
    if args.reserved:
        policy = policy.with_reserved(*args.reserved)
    return policy


def _render_text(catalog: Catalog) -> str:
    out: list[str] = []

    out.append("CONTRACTS")
    out.append("-" * 60)
    if not catalog.contracts:
        out.append("  (none)")
    for entry in catalog.contracts:
        phase = f" phase={entry.phase}" if entry.phase else ""
        out.append(f"  {entry.contract}  [{entry.kind}]{phase}")
        out.append(f"      provided by: {', '.join(entry.provided_by) or '-'}")
        if entry.required_by:
            out.append(f"      required by: {', '.join(entry.required_by)}")

    out.append("")
    out.append("EXTENSION POINTS")
    out.append("-" * 60)
    if not catalog.points:
        out.append("  (none)")
    for point in catalog.points:
        out.append(f"  {point.point}  [{point.policy}]")
        out.append(f"      contributors: {', '.join(point.contributors) or '-'}")

    out.append("")
    out.append("FINDINGS")
    out.append("-" * 60)
    if not catalog.findings:
        out.append("  (none)")
    for f in catalog.findings:
        out.append(f"  [{f.severity.upper()}] {f.code}: {f.subject}")
        out.append(f"      {f.message}")

    errors = len(catalog.errors())
    warnings = len(catalog.warnings())
    out.append("")
    out.append(f"summary: {errors} error(s), {warnings} warning(s)")
    return "\n".join(out)


def _render_json(catalog: Catalog) -> str:
    return json.dumps(
        {
            "contracts": [dataclasses.asdict(c) for c in catalog.contracts],
            "points": [dataclasses.asdict(p) for p in catalog.points],
            "findings": [dataclasses.asdict(f) for f in catalog.findings],
            "summary": {
                "errors": len(catalog.errors()),
                "warnings": len(catalog.warnings()),
            },
        },
        indent=2,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ctf-catalog",
        description="Dump the CTF ecosystem catalog and governance findings.",
    )
    parser.add_argument(
        "plugins",
        nargs="+",
        metavar="MODULE",
        help="importable module(s) that register CTF hookimpls",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="output format (default: text)",
    )
    parser.add_argument(
        "--reserved",
        nargs="*",
        default=[],
        metavar="CONTRACT",
        help="unprefixed contract names to treat as blessed (standard library)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit non-zero if there are ANY findings (warnings included)",
    )
    args = parser.parse_args(argv)

    # Make modules in the current working directory importable, so local plugin
    # packages can be named directly (like `python -m` would allow).
    cwd = os.getcwd()
    if cwd not in sys.path:
        sys.path.insert(0, cwd)

    contributions = []
    for path in args.plugins:
        try:
            contributions.append(inspect_plugin(_load(path)))
        except Exception as exc:  # noqa: BLE001 - surface import errors clearly
            print(f"error: could not load plugin {path!r}: {exc}", file=sys.stderr)
            return 2

    catalog = build_catalog(contributions, _policy(args))
    rendered = _render_json(catalog) if args.format == "json" else _render_text(catalog)
    print(rendered)

    if args.strict and catalog.findings:
        return 1
    return 1 if catalog.errors() else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
