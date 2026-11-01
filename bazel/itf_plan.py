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
"""The planner behind `itf_target`: compile a composition in plan-only mode, write the plan.

    itf_plan.py --target ecu.itf.yaml [--override lab.itf.yaml]... --pack docker... [--conftest conftest.py] --out ecu.plan.json

Both gates run exactly as `--itf-plan` runs them (strict shapes included) and nothing is constructed. A factory
label naming a pack that is not given with --pack fails. On a diagnostic the rendered report goes to stderr and
the exit status is 1.
"""

import argparse
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

from score.itf.core import (
    CompositionError,
    ConfigValidationFailed,
    PackNotFound,
    ResolutionFailed,
    Session,
    TargetNameClash,
)
from score.itf.core.adapters.definitions import definitions
from score.itf.core.frontends import composition

PLAN_KEYS = ("target", "action", "assumptions")


def _conftest(path: str):
    """A conftest file as a module, the way pytest would load it: the root holding the project's own parts."""
    spec = importlib.util.spec_from_file_location("conftest", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def check_packs(target: str, overrides: list[str], packs: list[str]) -> None:
    """Every factory label's pack must be one of `packs` (the `packs` of the `itf_target`)."""
    named = composition.factory_labels(composition.load_all(target, overrides))
    outside = sorted({label for label in named if label.split(".", 1)[0] not in (*packs, "project")})
    if outside:
        raise CompositionError(
            "capability factories from packs that are not in the itf_target's packs "
            f"({', '.join(sorted(packs)) or 'none'}): {', '.join(outside)}; add the pack to packs = [...]"
        )


def plan(target: str, overrides: list[str], packs: list[str], conftests: list[str] = ()) -> dict:
    """The plan of `target` with `overrides` merged over it: {"target", "action", "assumptions"}."""
    check_packs(target, overrides, packs)
    roots = [_conftest(path) for path in conftests]
    with tempfile.TemporaryDirectory() as run_dir:
        Session(
            roots,
            target=target,
            overrides=overrides,
            plan_only=True,
            strict_shapes=True,
            run_dir=run_dir,
            definitions=definitions(),
        ).resolve()
        document = json.loads((Path(run_dir) / "plan.json").read_text(encoding="utf-8"))
    return {key: document.get(key) for key in PLAN_KEYS}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--target", required=True, help="the composition (YAML)")
    parser.add_argument("--override", action="append", default=[], help="an override file, merged by role")
    parser.add_argument("--pack", action="append", default=[], help="a pack the composition may name")
    parser.add_argument("--conftest", action="append", default=[], help="a conftest with the project's own parts")
    parser.add_argument("--contracts", action="append", default=[], help="a directory of contract definitions")
    parser.add_argument("--out", required=True, help="where to write <name>.plan.json")
    options = parser.parse_args(argv)
    target = os.path.abspath(options.target)
    overrides = [os.path.abspath(path) for path in options.override]
    conftests = [os.path.abspath(path) for path in options.conftest]
    out = os.path.abspath(options.out)
    if options.contracts:
        os.environ["ITF_CONTRACTS_PATH"] = os.pathsep.join(os.path.abspath(path) for path in options.contracts)
    try:
        result = plan(target, overrides, options.pack, conftests)
    except ResolutionFailed as exc:
        print(f"ITF: plan failed at gate {exc.gate} ({exc.hook}) for {options.target}\n{exc.rendered}", file=sys.stderr)
        return 1
    except (CompositionError, ConfigValidationFailed, TargetNameClash, PackNotFound, ValueError) as exc:
        print(f"ITF: composition {options.target} does not compile\n{exc}", file=sys.stderr)
        return 1
    Path(out).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
