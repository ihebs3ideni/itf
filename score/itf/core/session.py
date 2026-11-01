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
"""The session: one catalog, one composition, one resolution, one bring-up.

Phase results accumulate here; artifacts are written even if a later phase fails, so partially
resolved runs remain inspectable.
"""

from __future__ import annotations

import contextlib
import time
from pathlib import Path

from . import gating
from . import octo
from .engine.assumptions import describe_assumed
from .engine.bringup import ExecutionError, Observation, ProbeFailed, execute, observe
from .engine.close import SessionView, UnwindReport, run_startup_checks, run_teardown_hooks, unwind
from .engine.failure import Failure, banner, bring_up_failure, checks_failure, teardown_failure
from .engine.realize import Realization, default_resolver
from .engine import packs as pack_loader
from .engine.metadata import PROJECT_PACK
from .engine.registry import ORIGINS, expand, register_modules
from .frontends import composition
from .frontends.target_source import TargetSource, as_source
from .engine.publish import publish
from .engine.render import render
from .engine.labels import label_steps, node_label
from .engine.scopes import ROOT, display, display_json
from .engine.log import (
    log_plan_warnings,
    log_checks,
    log_config_issues,
    log_event,
    log_gating,
    log_phase,
    log_resolution,
    log_target_summary,
    log_teardown,
    log_unwind,
    log_drift,
)
from .process import ProcessWrapper
from .octo import GoalClaim
from .target import Target, name_clashes, target_view

PRECEDENCE = ORIGINS
_RECORDED = frozenset({"state_probed", "action_started", "action_finished", "action_skipped"})


class ResolutionFailed(Exception):
    def __init__(self, gate: int, hook: str, diagnostics, rendered: str):
        super().__init__(rendered)
        self.gate = gate
        self.hook = hook
        self.diagnostics = diagnostics
        self.rendered = rendered


class NotReady(Exception):
    """Bring-up or a startup check failed. `failure` is the report to show a person (None when unknown)."""

    def __init__(self, message: str, failure=None):
        super().__init__(message)
        self.failure = failure


class ConfigValidationFailed(Exception):
    def __init__(self, issues):
        self.issues = tuple(issues)
        super().__init__(
            display(
                "config validation failed:\n"
                + "\n".join(f"  {node_label(ref, provider)}: {message}" for ref, provider, message in self.issues)
            )
        )


class TargetNameClash(Exception):
    def __init__(self, clashes):
        self.clashes = tuple(clashes)
        super().__init__("ambiguous names on the target handle:\n" + "\n".join(f"  {c}" for c in self.clashes))


def _roots(roots) -> list:
    """Without pytest: `roots` play the root conftest; their `pytest_plugins` are followed as pytest would."""
    from .engine.registry import follow

    return list(follow((r, "conftest") for r in roots))


def log_composition(target, overrides) -> None:
    import logging

    logging.getLogger("score.itf.core").info(
        "composition: %s%s",
        target.describe(),
        "".join(f"; override {o.describe()}" for o in overrides),
    )


class Session:
    """One run. `target` (a path, inline text or TargetSource) is the composition; `overrides` are further
    compositions merged over it by role. Packs load from the factory labels the composition names; project
    capabilities and actions come from `roots` (playing the root conftest, their `pytest_plugins` followed) or
    `contributors`, the (module, origin) pairs a runner already loaded. Without a target the composition is
    empty, which is valid. `definitions` (contract name -> `gating.Definition`) is optional: with it a plan warns
    about deprecated contracts; nothing needs it."""

    def __init__(
        self,
        roots=(),
        *,
        contributors=None,
        target=None,
        overrides=(),
        plan_only: bool = False,
        gating: str = "skip",
        reuse: str = "probe",
        on_exit: str = "unwind",
        strict_shapes: bool = False,
        definitions=None,
        run_dir=None,
        resolver=None,
    ):
        self._roots = [roots] if isinstance(roots, str) else list(roots)
        self._contributors = contributors
        self.target_source: TargetSource | None = as_source(target) if target is not None else None
        if isinstance(overrides, (str, TargetSource)):
            overrides = [overrides]
        self.override_sources = tuple(as_source(o, origin="overrides=") for o in overrides)
        if self.override_sources and self.target_source is None:
            raise ValueError("overrides need a target: Session(target=..., overrides=[...])")
        self.plan_only = plan_only
        self.gating = gating
        self.reuse = reuse
        self.on_exit = on_exit
        self.strict_shapes = strict_shapes
        self.definitions = dict(definitions) if definitions else {}
        self.run_dir = Path(run_dir) if run_dir is not None else Path("itf-run")
        self._resolver = resolver or default_resolver

        self._registry = None
        self._catalog = None
        self._setup_claims: frozenset = frozenset()
        self._init_claims: frozenset = frozenset()
        self._target_plan = None
        self._action_plan = None
        self._full_plan = None
        self._reached_goals: frozenset = frozenset()
        self._realization = None
        self._factory_majors: dict = {}  # factory label -> the major it offers (absent: unknown)
        self._composition = None
        self._compiled = None
        self._warnings: list = []
        self._pre_observation: Observation | None = None
        self._last_observed: frozenset = frozenset()
        self._assumed: tuple = ()
        self._target: Target | None = None
        self._resolution_failure: ResolutionFailed | None = None
        self._config_issues: tuple = ()
        self._gating_decisions: list = []
        self._run_report = None
        self._check_results: tuple = ()
        self._teardown_results: tuple = ()
        self._unwind_report: UnwindReport | None = None
        self._leaked_processes: tuple[str, ...] = ()
        self._ready = False
        self._closed = False
        self._artifact_cache: dict = {}
        self._probe_stats: dict = {}  # phase -> {count, ms, runs}
        self._drift: tuple = ()  # ({phase, dropped, appeared}, ...)
        self._events: tuple = ()  # ({phase, kind, t, ...}, ...): what the evidence record is built from
        self._failure_text: str = ""

    def _fail(self, gate: int, hook: str, diagnostics) -> None:
        roles = self._compiled.roles if self._compiled is not None else {}
        text = render(diagnostics, gate=gate, hook=hook, catalog=self._catalog, roles=roles)
        exc = ResolutionFailed(gate, hook, diagnostics, text)
        self._resolution_failure = exc
        log_resolution(gate, hook, False, diagnostics)
        raise exc

    def resolve(self) -> "Session":
        # Two gates, in order, because the second depends on the first. Gate 1 decides what must exist: which
        # factory fills which role, as a target plan. Gate 2 decides what must happen on it: the ordered actions
        # that make the goal states true. Nothing is constructed until bring_up, so the whole of resolve() is
        # safe to run without hardware (`--itf-plan`).
        log_phase("resolve")
        try:
            doc = (
                composition.load_all(self.target_source, self.override_sources)
                if self.target_source
                else (composition.load({}))
            )
            self._composition = doc
            if self.target_source is not None:
                log_composition(self.target_source, self.override_sources)
            modules = composition.pack_modules(doc)
            pack_entries = [
                pack_loader.load(name, modules) for name in composition.packs_of(doc) if name != PROJECT_PACK
            ]
            project = expand(self._contributors) if self._contributors is not None else None
            if project is not None:
                registry = register_modules([*expand(pack_entries), *project])
            else:
                registry = register_modules([*expand(pack_entries), *_roots(self._roots)])
            self._registry = registry
            catalog = publish(registry)
            self._catalog = catalog
            self._factory_majors = {l: f.major for l, f in catalog.factories.items() if f.major is not None}

            compiled = composition.compile(doc, catalog)
            self._compiled = compiled
            setup_claims = compiled.setup | frozenset(catalog.providers)
            self._setup_claims = setup_claims
            target_res = octo.resolve_target(
                setup_claims,
                precedence=PRECEDENCE,
                max_derivation_depth=0,
                strict_shapes=self.strict_shapes,
            )
            if not target_res.ok():
                self._fail(1, "capabilities", target_res.diagnostics)
            self._target_plan = target_res.plan
            self._check_majors(target_res.plan, catalog)
            log_resolution(1, "capabilities", True, ())
            log_target_summary(target_res.plan)
            self._warn(gating.deprecations(target_res.plan, self.definitions))
            # Settings are validated against each factory's schema here, between the gates, so a typo in a
            # composition fails at plan time with the role named, not when the factory is first used.
            issues = []
            for node in target_res.plan.nodes:
                schema = catalog.config_schemas.get(node.provider)
                if schema is not None:
                    issues.extend((node.ref, node.provider, message) for message in schema.validate(dict(node.config)))
            self._config_issues = tuple(issues)
            if issues:
                log_config_issues(issues)
                raise ConfigValidationFailed(issues)

            init_claims = compiled.init
            self._init_claims = init_claims
            scopes = frozenset(s for s in compiled.roles if s != ROOT)
            # `target.<x>` must mean one thing: a role named like a scope or a handle member would be
            # ambiguous, so it is rejected up front instead of resolving to whichever wins.
            clashes = name_clashes(target_res.plan, scopes)
            if clashes:
                raise TargetNameClash(clashes)
            self._realization = Realization(target_res.plan, resolver=self._resolver)

            action_res = self._resolve_gate2(init_claims, target_res.plan)
            self._action_plan = action_res.plan
            log_resolution(2, "states", True, ())
            self._assumed = describe_assumed(action_res.plan, init_claims)
            self._last_observed = self._pre_observation.holds if self._pre_observation else frozenset()
            self._target = Target(self, scopes)

            if self.plan_only:
                self._dry_run_check()
        finally:
            self._write_artifacts()
        return self

    def _check_majors(self, plan, catalog) -> None:
        """When a factory offers `@major` and a slot expects one, they must agree."""
        problems = []
        for node in plan.nodes:
            expected = catalog.factories[node.provider].need_majors
            for slot, ref in node.bindings:
                provider = plan.node(ref).provider
                offered = catalog.factories[provider].major
                if slot in expected and offered is not None and expected[slot] != offered:
                    problems.append(
                        f"{display(node.ref)} ({node.provider}) expects its {slot} at @{expected[slot]} but "
                        f"{display(ref)} ({provider}) offers @{offered}"
                    )
        if problems:
            raise composition.CompositionError("contract major mismatch:\n  " + "\n  ".join(problems))

    def _warn(self, messages) -> None:
        fresh = [m for m in messages if m not in self._warnings]
        if fresh:
            self._warnings.extend(fresh)
            log_plan_warnings(fresh)

    @property
    def warnings(self) -> tuple[str, ...]:
        return tuple(self._warnings)

    def _resolve_gate2(self, init_claims, target_plan):
        discover_res = octo.resolve_actions(
            init_claims,
            target_plan,
            precedence=PRECEDENCE,
            observed_states=frozenset(),
            strict_shapes=self.strict_shapes,
        )
        if not discover_res.ok():
            self._fail(2, "states", discover_res.diagnostics)
        self._full_plan = discover_res.plan
        if self.plan_only or self.reuse == "fresh":
            return discover_res

        # reuse == "probe": probe the full plan, then re-plan the delta.
        meter = self._meter(log_event)
        pre_observation = observe(discover_res.plan, self._realization, observer=meter, resolver=self._resolver)
        self._record_probes("before_bring_up", meter)
        self._pre_observation = pre_observation
        action_res = octo.resolve_actions(
            init_claims,
            target_plan,
            precedence=PRECEDENCE,
            observed_states=pre_observation.holds,
            strict_shapes=self.strict_shapes,
        )
        if not action_res.ok():
            self._fail(2, "states", action_res.diagnostics)
        return action_res

    def _dry_run_check(self) -> None:
        """A dry run resolves every `impl`, teardown and probe reference; constructs nothing (A-4.4)."""
        used_providers = {n.provider for n in self._target_plan.nodes}
        extra = tuple(s.impl for s in self._action_plan.steps)
        extra += tuple(probe for s in self._action_plan.steps for _, probe in s.state_probes())
        self._realization.resolve_all(extra_impls=extra)

    def select(self, requirements: dict) -> dict:
        """`requirements`: test id -> tuple[Requirement, ...]. Returns test id -> GatingDecision.
        A requirement without `scope` is checked against the root scope only."""
        known = {ROOT, *self._target.scopes()}
        decisions = {}
        for test_id, reqs in requirements.items():
            decision = gating.GatingDecision(True)
            for req in reqs:
                scope = req.scope or ROOT
                if scope not in known:
                    decision = gating.GatingDecision(False, f"target has no scope {req.scope!r}")
                    break
                d = gating.evaluate(req, self._target_plan, scope, self._factory_majors)
                if not d.selected:
                    decision = d
                    break
            decisions[test_id] = decision
        self._gating_decisions = list(decisions.items())
        log_gating(decisions)
        self._write_artifacts()
        return decisions

    def bring_up(self) -> None:
        if self.plan_only:
            raise RuntimeError("a plan_only session does not bring up")
        # Bring-up probes first (a state already holding is reused), then runs the delta. Startup checks
        # (itf_verify) run last and only after the states hold, so a check failure means the target is
        # unhealthy, not that it is still being built. Essential check failures stop the session before any
        # test runs.
        log_phase("bring-up")
        observation = self._pre_observation or Observation(frozenset(), ())
        meter = self._meter(log_event)
        try:
            self._run_report = execute(
                self._action_plan, self._realization, observation, observer=meter, resolver=self._resolver
            )
        except (ExecutionError, ProbeFailed) as exc:
            failure = bring_up_failure(exc, self._action_plan, self._target_plan, self.run_dir)
            self._failure_text = failure.render()
            raise NotReady(display(str(exc)), failure) from exc
        finally:
            self._record_probes("bring_up", meter)
            self._write_artifacts()

        self._last_observed = self._observe_and_check("after_bring_up", self._run_report.holds)
        log_phase("startup checks")
        view = SessionView(self)
        self._check_results = run_startup_checks(self._registry, view)
        log_checks(self._check_results)
        self._write_artifacts()
        failing = [c for c in self._check_results if c.essential and not c.ok]
        if failing:
            failure = checks_failure(self._check_results, self.run_dir)
            self._failure_text = failure.render()
            raise NotReady(
                f"{len(failing)} essential startup check(s) failed: {', '.join(c.name for c in failing)}", failure
            )
        self._ready = True

    @property
    def target(self) -> Target:
        if self._target is None:
            raise RuntimeError("the session has not resolved yet")
        return self._target

    def reach(self, *states: str, assume: tuple[str, ...] = (), reason: str = "", owner: str = ""):
        """Re-plan and execute the delta to reach `states`: `token` or `:token` is the root scope,
        `dev1:token` a device. `assume` (same form) bypasses a dependency's producer for this call
        only, without evidence that it holds; the plan records which ids were taken on faith and,
        via `owner`/`reason`, who said so (D-30).
        """
        return self._reach(states, assume=assume, reason=reason, owner=owner)

    def renew(self, *nodes: str):
        """Rebuild nodes from scratch, then reach every goal so far again: `name` or `.name` is a
        root node, `dev1.name` a device's. Each node and every realized node bound to it is
        dismantled; a state delivered through one of them, or requiring such a state, is not
        taken as holding even if its probe says so, so its producer runs again.
        """
        # Renewal is a primitive, not a mode: the caller decides when (a fixture, a test). Nothing in ITF renews
        # on its own, so ITF never fights pytest's own fixture scoping.
        refs = [n[1:] if n.startswith(".") else n for n in nodes]
        refs = [r if "." in r else f"{ROOT}.{r}" for r in refs]
        for ref in refs:
            if not self._realization.has(ref):
                raise KeyError(f"target has no node {ref!r}")
        log_phase(f"renew {', '.join(refs)}")
        dismantled = frozenset(self._realization.discard(refs))
        # A probe cannot be trusted for a state whose evidence ran through a dismantled node (it may read
        # state that lives outside the new object, e.g. a port the old container still held). Such states, and
        # whatever requires them, are re-delivered by their producers rather than taken as holding.
        resolve = self._target_plan.resolve
        tainted = {
            d
            for step in self._full_plan.steps
            if any(resolve(ref) in dismantled for _, ref in step.uses)
            for d in step.delivers
        }
        grew = True
        while grew:
            grew = False
            for step in self._full_plan.steps:
                if set(step.requires) & tainted and not set(step.delivers) <= tainted:
                    tainted.update(step.delivers)
                    grew = True
        return self._reach((), forget=frozenset(tainted))

    def _qualify(self, state: str) -> str:
        """`state` (`token`, `:token` or `scope:token`) as `scope:token`."""
        scope, colon, token = state.rpartition(":")
        return f"{scope or ROOT}:{token}"

    def _reach(self, states, *, assume=(), reason: str = "", owner: str = "", forget: frozenset = frozenset()):
        qualify = self._qualify
        wanted = [qualify(s) for s in states]
        assumed_ids = frozenset(qualify(s) for s in assume)
        known = {ROOT, *self.target.scopes()}
        unknown = sorted({r.split(":", 1)[0] for r in (*wanted, *assumed_ids)} - known)
        if unknown:
            raise KeyError(
                f"target has no scope {', '.join(map(repr, unknown))}; "
                f"scopes: {', '.join(self.target.scopes()) or '(none)'}"
            )
        if wanted:
            log_phase(f"reach {', '.join(wanted)}")
        by_scope: dict[str, set] = {}
        for ref in wanted:
            scope, token = ref.split(":", 1)
            by_scope.setdefault(scope, set()).add(token)
        extra_goals = {GoalClaim(scope=s, states=frozenset(t), origin="policy") for s, t in by_scope.items()}
        claims = self._init_claims | extra_goals
        # The probe universe is every step any goal so far needs, never just the last delta:
        # otherwise a state pruned from one delta would go unobserved and be re-run by the next.
        self._reached_goals |= extra_goals
        full = octo.resolve_actions(
            self._init_claims | self._reached_goals,
            self._target_plan,
            precedence=PRECEDENCE,
            observed_states=frozenset(),
            assumed_states=assumed_ids,
            strict_shapes=self.strict_shapes,
        )
        if not full.ok():
            self._fail(2, "states", full.diagnostics)
        self._full_plan = full.plan
        meter = self._meter()
        observation = observe(self._full_plan, self._realization, observer=meter, resolver=self._resolver)
        self._record_probes("reach_before", meter)
        if forget:
            observation = Observation(observation.holds - forget, observation.errors)
        res = octo.resolve_actions(
            claims,
            self._target_plan,
            precedence=PRECEDENCE,
            observed_states=observation.holds,
            assumed_states=assumed_ids,
            strict_shapes=self.strict_shapes,
        )
        if not res.ok():
            self._fail(2, "states", res.diagnostics)
        log_resolution(2, "states", True, ())
        meter = self._meter(log_event)
        try:
            report = execute(res.plan, self._realization, observation, observer=meter, resolver=self._resolver)
        finally:
            self._record_probes("reach_verify", meter)
        self._action_plan = res.plan
        self._assumed = describe_assumed(
            res.plan,
            claims,
            request_ids=assumed_ids,
            request_owner=owner,
            request_reason=reason,
        )
        self._run_report = report
        self._last_observed = self._observe_and_check("after_reach", report.holds)
        self._write_artifacts()
        return report

    def _meter(self, forward=None):
        """An observer that counts probe calls and their time, then forwards every event."""
        counts = {"count": 0, "ms": 0.0}
        events: list = []

        def observer(kind: str, data: dict) -> None:
            if kind in _RECORDED:
                events.append({"kind": kind, "t": time.time(), **data})
            if kind == "state_probed":
                counts["count"] += 1
                counts["ms"] += data.get("ms", 0.0)
            if forward is not None:
                forward(kind, data)

        observer.counts = counts
        observer.events = events
        return observer

    def _record_probes(self, phase: str, meter) -> None:
        # replaced, not mutated: the artifact cache compares by identity
        self._events = self._events + tuple({"phase": phase, **e} for e in meter.events)
        meter.events.clear()
        prev = self._probe_stats.get(phase, {"count": 0, "ms": 0.0, "runs": 0})
        self._probe_stats = {
            **self._probe_stats,
            phase: {
                "count": prev["count"] + meter.counts["count"],
                "ms": round(prev["ms"] + meter.counts["ms"], 3),
                "runs": prev["runs"] + 1,
            },
        }

    def _observe_and_check(self, phase: str, expected: frozenset) -> frozenset:
        """Re-probe the full plan and report drift: a probed state that should hold and does not
        (dropped, e.g. an undeclared side effect) or holds but was not expected (appeared)."""
        meter = self._meter()
        actual = observe(self._full_plan, self._realization, observer=meter, resolver=self._resolver).holds
        self._record_probes(phase, meter)
        probed = {d for s in self._full_plan.steps for d, _ in s.state_probes()}
        dropped, appeared = sorted((expected - actual) & probed), sorted((actual - expected) & probed)
        if dropped or appeared:
            entry = {"phase": phase, "dropped": dropped, "appeared": appeared}
            self._drift = self._drift + (entry,)
            log_drift(entry)
        return actual

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        # Order matters: teardown hooks first, while the target still runs (they collect evidence from it),
        # then unwind dismantles what was built. Idempotent, so an error path and the normal path may both
        # call close().
        log_phase("close")
        if self._registry is not None:
            view = SessionView(self)
            self._teardown_results = run_teardown_hooks(self._registry, view)
            log_teardown(self._teardown_results)
        if self._target_plan is not None and self._full_plan is not None and self._realization is not None:
            meter = self._meter()
            self._unwind_report = unwind(
                self._target_plan,
                self._full_plan,
                self._realization,
                self._catalog,
                on_exit=self.on_exit,
                resolver=self._resolver,
                observer=meter,
            )
            self._record_probes("unwind", meter)
            log_unwind(self._unwind_report)
        # Anything a provider, a test or a failed teardown left running is stopped now, and reported: a run
        # must not leave host processes behind, and a leak is a defect in whoever started it.
        self._leaked_processes = ProcessWrapper.reap()
        self._write_artifacts()
        self._write_evidence()

    def close_problems(self) -> Failure | None:
        """The report for what went wrong while closing (a failing teardown hook, a node that would not
        dismantle), or None. Read after close(); closing itself never raises for these."""
        return teardown_failure(self._teardown_results, self._unwind_report, self.run_dir, self._leaked_processes)

    def _write_evidence(self) -> None:
        # Evidence is a report about the run, never a reason for closing to fail.
        try:
            from .engine.evidence import write_evidence

            write_evidence(self.run_dir, self)
        except Exception as exc:  # noqa: BLE001
            log_event("evidence_failed", {"error": repr(exc)})

    def _write_artifacts(self) -> None:
        from .artifacts import write_artifacts

        write_artifacts(self.run_dir, self, cache=self._artifact_cache)


class DescribeResult:
    def __init__(self, session: Session):
        self._session = session

    @property
    def target_plan(self):
        return self._session._target_plan

    @property
    def action_plan(self):
        return self._session._action_plan

    def render(self) -> str:
        import json
        from .engine.config import redact_target

        catalog = self._session._catalog
        tp = redact_target(self._session._target_plan, getattr(catalog, "config_schemas", {}))
        ap = self._session._action_plan
        return "\n".join(
            [
                "Target plan:",
                json.dumps(target_view(tp), indent=2) if tp is not None else "(none)",
                "Action plan:",
                json.dumps(display_json(label_steps(ap.to_json(), catalog)), indent=2) if ap is not None else "(none)",
                *(["Warnings:", *(f"  {w}" for w in self._session.warnings)] if self._session.warnings else []),
            ]
        )


def describe(roots=(), **opts) -> DescribeResult:
    opts["plan_only"] = True
    session = Session(roots, **opts)
    session.resolve()
    return DescribeResult(session)


@contextlib.contextmanager
def compose(roots=(), **opts):
    session = Session(roots, **opts)
    try:
        session.resolve()
        session.bring_up()
        yield session
    finally:
        session.close()
