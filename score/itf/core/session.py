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
"""The session: one catalog, one recipe, one resolution, one bring-up
(docs/octo-kit/12-spec-itf-core.md §2, §3, §6).

Phase results accumulate here; artifacts are written even if a later phase fails, so partially
resolved runs remain inspectable.
"""

from __future__ import annotations

import contextlib
from pathlib import Path

from . import gating
from . import octo
from .engine.assumptions import describe_assumed
from .engine.bringup import ExecutionError, Observation, ProbeFailed, execute, observe
from .engine.close import SessionView, UnwindReport, run_startup_checks, run_teardown_hooks, unwind
from .engine.collect import collect_init, collect_setup
from .engine.failure import Failure, banner, bring_up_failure, checks_failure, teardown_failure
from .engine.realize import Realization, default_resolver
from .engine.registry import ORIGINS, register, register_modules
from .engine.publish import publish
from .engine.render import render
from .engine.scopes import ROOT, display, display_json, state_ref
from .engine.log import (
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
                + "\n".join(f"  {ref} ({provider}): {message}" for ref, provider, message in self.issues)
            )
        )


class TargetNameClash(Exception):
    def __init__(self, clashes):
        self.clashes = tuple(clashes)
        super().__init__("ambiguous names on the target handle:\n" + "\n".join(f"  {c}" for c in self.clashes))


def _device_scopes(claims) -> frozenset:
    return frozenset(s for s in (getattr(c, "scope", "") for c in claims) if s and s != ROOT)


class Session:
    """One run. `roots` play the root conftest (their `pytest_plugins` are followed); the pytest
    adapter instead passes `contributors`, the (module, origin) pairs pytest already loaded."""

    def __init__(
        self,
        roots=(),
        *,
        contributors=None,
        plan_only: bool = False,
        gating: str = "skip",
        reuse: str = "probe",
        on_exit: str = "unwind",
        strict_shapes: bool = False,
        run_dir=None,
        resolver=None,
    ):
        self._roots = [roots] if isinstance(roots, str) else list(roots)
        self._contributors = contributors
        self.plan_only = plan_only
        self.gating = gating
        self.reuse = reuse
        self.on_exit = on_exit
        self.strict_shapes = strict_shapes
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
        self._provider_gives: dict = {}
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

    def _fail(self, gate: int, hook: str, diagnostics) -> None:
        text = render(diagnostics, gate=gate, hook=hook)
        exc = ResolutionFailed(gate, hook, diagnostics, text)
        self._resolution_failure = exc
        log_resolution(gate, hook, False, diagnostics)
        raise exc

    def resolve(self) -> "Session":
        # Two gates, in order, because the second depends on the first. Gate 1 (itf_setup) decides what must
        # exist: which providers fill which contracts, as a target plan. Gate 2 (itf_init) decides what must
        # happen on it: the ordered actions that bring states up. Nothing is constructed until bring_up, so
        # the whole of resolve() is safe to run without hardware (`--itf-plan`).
        log_phase("resolve")
        try:
            if self._contributors is not None:
                registry = register_modules(self._contributors)
            else:
                registry = register(self._roots)
            self._registry = registry
            catalog = publish(registry)
            self._catalog = catalog
            self._provider_gives = {p.name: p.gives for p in catalog.providers}

            setup_claims = collect_setup(registry, catalog) | frozenset(catalog.providers)
            self._setup_claims = setup_claims
            target_res = octo.resolve_target(
                setup_claims,
                precedence=PRECEDENCE,
                strict_shapes=self.strict_shapes,
            )
            if not target_res.ok():
                self._fail(1, "itf_setup", target_res.diagnostics)
            self._target_plan = target_res.plan
            log_resolution(1, "itf_setup", True, ())
            log_target_summary(target_res.plan)
            # Config is validated against each provider's schema here, between the gates, so a typo in a
            # recipe fails at plan time with the node named, not when the provider is first used.
            issues = []
            for node in target_res.plan.nodes:
                schema = catalog.config_schemas.get(node.provider)
                if schema is not None:
                    issues.extend((node.ref, node.provider, message) for message in schema.validate(dict(node.config)))
            self._config_issues = tuple(issues)
            if issues:
                log_config_issues(issues)
                raise ConfigValidationFailed(issues)

            init_claims = collect_init(registry, catalog, target_res.plan) | frozenset(catalog.actions)
            self._init_claims = init_claims
            scopes = _device_scopes(setup_claims | init_claims) | (set(target_res.plan.scopes()) - {ROOT})
            # `target.<x>` must mean one thing: a node named like a device scope or a handle member would be
            # ambiguous, so it is rejected up front instead of resolving to whichever wins.
            clashes = name_clashes(target_res.plan, scopes)
            if clashes:
                raise TargetNameClash(clashes)
            self._realization = Realization(target_res.plan, resolver=self._resolver)

            action_res = self._resolve_gate2(init_claims, target_res.plan)
            self._action_plan = action_res.plan
            log_resolution(2, "itf_init", True, ())
            self._assumed = describe_assumed(action_res.plan, init_claims)
            self._last_observed = self._pre_observation.holds if self._pre_observation else frozenset()
            self._target = Target(self, scopes)

            if self.plan_only:
                self._dry_run_check()
        finally:
            self._write_artifacts()
        return self

    def _resolve_gate2(self, init_claims, target_plan):
        discover_res = octo.resolve_actions(
            init_claims,
            target_plan,
            precedence=PRECEDENCE,
            observed_states=frozenset(),
            strict_shapes=self.strict_shapes,
        )
        if not discover_res.ok():
            self._fail(2, "itf_init", discover_res.diagnostics)
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
            self._fail(2, "itf_init", action_res.diagnostics)
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
                d = gating.evaluate(req, self._target_plan, scope, self._provider_gives)
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
            raise NotReady(
                display(str(exc)), bring_up_failure(exc, self._action_plan, self._target_plan, self.run_dir)
            ) from exc
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
            raise NotReady(
                f"{len(failing)} essential startup check(s) failed: {', '.join(c.name for c in failing)}",
                checks_failure(self._check_results, self.run_dir),
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

    def _reach(self, states, *, assume=(), reason: str = "", owner: str = "", forget: frozenset = frozenset()):
        qualify = lambda s: state_ref(s if ":" in s else f":{s}")
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
            self._fail(2, "itf_init", full.diagnostics)
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
            self._fail(2, "itf_init", res.diagnostics)
        log_resolution(2, "itf_init", True, ())
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

        def observer(kind: str, data: dict) -> None:
            if kind == "state_probed":
                counts["count"] += 1
                counts["ms"] += data.get("ms", 0.0)
            if forward is not None:
                forward(kind, data)

        observer.counts = counts
        return observer

    def _record_probes(self, phase: str, meter) -> None:
        # replaced, not mutated: the artifact cache compares by identity
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

    def close_problems(self) -> Failure | None:
        """The report for what went wrong while closing (a failing teardown hook, a node that would not
        dismantle), or None. Read after close(); closing itself never raises for these."""
        return teardown_failure(self._teardown_results, self._unwind_report, self.run_dir, self._leaked_processes)

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
                json.dumps(display_json(ap.to_json()), indent=2) if ap is not None else "(none)",
            ]
        )


def describe(roots, **opts) -> DescribeResult:
    opts["plan_only"] = True
    session = Session(roots, **opts)
    session.resolve()
    return DescribeResult(session)


@contextlib.contextmanager
def compose(roots, **opts):
    session = Session(roots, **opts)
    try:
        session.resolve()
        session.bring_up()
        yield session
    finally:
        session.close()
