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
"""Persist partial results even after a failed gate or interrupted bring-up.

JSON remains the source of facts; the HTML report projects the same resolved plans for readers.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from .engine.render import render
from .engine.report import render_target_html
from .engine.config import redact_target
from .engine.labels import label_steps, node_label
from .engine.scopes import display, display_json
from .octo import GoalClaim, claims_to_json
from .target import target_view


def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True, default=str), encoding="utf-8")


def _to_jsonable(obj):
    if dataclasses.is_dataclass(obj):
        d = {f.name: _to_jsonable(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
        d["_kind"] = type(obj).__name__
        return d
    if isinstance(obj, frozenset):
        return [_to_jsonable(x) for x in sorted(obj, key=repr)]
    if isinstance(obj, (tuple, list)):
        return [_to_jsonable(x) for x in obj]
    return obj


def _goal_refs(init_claims) -> tuple[str, ...]:
    return tuple(sorted(f"{c.scope}:{t}" for c in init_claims if isinstance(c, GoalClaim) for t in c.states))


def _changed(cache: dict | None, name: str, *sources) -> bool:
    """True unless `name` was last written from these very objects; session state is replaced,
    never mutated, so identity says whether a file's content can have changed."""
    if cache is None:
        return True
    prev = cache.get(name)
    if prev is not None and len(prev) == len(sources) and all(a is b for a, b in zip(prev, sources)):
        return False
    cache[name] = sources
    return True


def write_artifacts(run_dir: Path, session, *, cache: dict | None = None) -> None:
    """Write every artifact; with `cache`, skip the ones whose inputs are unchanged since the last call."""
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    catalog = getattr(session, "_catalog", None)
    schemas = getattr(catalog, "config_schemas", {})
    original_target = getattr(session, "_target_plan", None)
    selected = {node.ref: node.provider for node in original_target.nodes} if original_target else {}

    def safe_config(provider, config):
        schema = schemas.get(provider)
        return schema.redact(config) if schema else config

    setup_claims = getattr(session, "_setup_claims", None) or ()
    init_claims = getattr(session, "_init_claims", None) or ()
    config_issues = getattr(session, "_config_issues", ())
    if _changed(cache, "claims.json", setup_claims, init_claims, original_target, catalog):
        _write_claims(run_dir, setup_claims, init_claims, safe_config, selected)

    target_plan = redact_target(original_target, schemas)
    action_plan = getattr(session, "_action_plan", None)
    assumed = getattr(session, "_assumed", None) or ()
    handle = getattr(session, "_target", None)
    if _changed(cache, "plan.json", original_target, action_plan, assumed, handle, catalog, config_issues):
        _write_json(
            run_dir / "plan.json",
            {
                "target": target_view(target_plan, handle.scopes() if handle else ())
                if target_plan is not None
                else None,
                "action": display_json(label_steps(action_plan.to_json(), catalog))
                if action_plan is not None
                else None,
                "assumptions": display_json(list(assumed)),
                "config_schemas": {name: schema.describe() for name, schema in sorted(schemas.items())},
                "config_issues": [
                    dict(ref=display(ref), provider=provider, message=message)
                    for ref, provider, message in config_issues
                ],
            },
        )

    run_report = getattr(session, "_run_report", None)
    failure = getattr(session, "_resolution_failure", None)
    if target_plan is not None and _changed(
        cache, "target.html", original_target, action_plan, run_report, catalog, config_issues, failure
    ):
        (run_dir / "target.html").write_text(
            render_target_html(
                target_plan,
                action_plan,
                title=f"itf target · {run_dir.name}",
                run_report=run_report,
                config_schemas={name: schema.describe() for name, schema in schemas.items()},
                config_issues=config_issues,
                failure=failure,
                goals=_goal_refs(init_claims),
            ),
            encoding="utf-8",
        )

    if _changed(cache, "diagnostics.txt", failure, config_issues):
        diagnostics_text = ""
        if failure is not None:
            roles = session._compiled.roles if getattr(session, "_compiled", None) is not None else {}
            diagnostics_text = render(
                failure.diagnostics, gate=failure.gate, hook=failure.hook, catalog=catalog, roles=roles
            )
        if config_issues:
            diagnostics_text += "\n".join(
                f"{node_label(display(ref), provider)}: {message}" for ref, provider, message in config_issues
            )
        (run_dir / "diagnostics.txt").write_text(diagnostics_text, encoding="utf-8")

    gating_decisions = getattr(session, "_gating_decisions", None) or ()
    if _changed(cache, "gating.json", gating_decisions):
        _write_json(
            run_dir / "gating.json",
            [{"test": name, "selected": dec.selected, "reason": dec.reason} for name, dec in gating_decisions],
        )

    check_results = getattr(session, "_check_results", None) or ()
    pre_observation = getattr(session, "_pre_observation", None)
    probe_stats = getattr(session, "_probe_stats", None)
    drift = getattr(session, "_drift", None)
    if _changed(cache, "run.json", run_report, check_results, pre_observation, probe_stats, drift):
        _write_json(
            run_dir / "run.json",
            display_json(
                {
                    "probed_before_gate2": sorted(pre_observation.holds) if pre_observation else [],
                    "executed": list(run_report.executed) if run_report else [],
                    "skipped": list(run_report.skipped) if run_report else [],
                    "checks": [
                        {"name": c.name, "ok": c.ok, "detail": c.detail, "essential": c.essential}
                        for c in check_results
                    ],
                    "probes": probe_stats or {},
                    "drift": list(drift or ()),
                }
            ),
        )

    unwind_report = getattr(session, "_unwind_report", None)
    teardown_results = getattr(session, "_teardown_results", None) or ()
    if _changed(cache, "unwind.json", unwind_report, teardown_results):
        _write_json(
            run_dir / "unwind.json",
            display_json(
                {
                    "teardown_hooks": [{"name": n, "ok": ok, "error": err} for n, ok, err in teardown_results],
                    "kept": unwind_report.kept if unwind_report else None,
                    "probed": list(unwind_report.probed) if unwind_report else [],
                    "dismantled": list(unwind_report.dismantled) if unwind_report else [],
                    "errors": [{"ref": r, "error": e} for r, e in unwind_report.errors] if unwind_report else [],
                }
            ),
        )


def _write_claims(run_dir: Path, setup_claims, init_claims, safe_config, selected) -> None:
    setup_json = claims_to_json(setup_claims)
    for entry in setup_json:
        if entry.get("_kind") == "NodeClaim":
            ref = f"{entry['scope']}.{entry['name']}"
            entry["config"] = safe_config(entry.get("using") or selected.get(ref), entry["config"])
    _write_json(
        run_dir / "claims.json",
        {
            "setup": setup_json,
            "init": claims_to_json(init_claims),
        },
    )
