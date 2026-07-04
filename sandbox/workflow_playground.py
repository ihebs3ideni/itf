"""Pluggy workflow bridge for ITF experiments.

It stays separate from pytest and is advanced from conftest at hook
boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Sequence

import pluggy

PROJECT_NAME = "itf_workflow_playground"
hookspec = pluggy.HookspecMarker(PROJECT_NAME)
hookimpl = pluggy.HookimplMarker(PROJECT_NAME)

DEFAULT_PHASES: tuple[str, ...] = (
    "collect_inputs",
    "setup_environment",
    "create_target",
    "declare_bootstrap_capabilities",
    "compose_bootstrap_capabilities",
    "flash_target",
    "start_target",
    "declare_runtime_capabilities",
    "compose_runtime_capabilities",
    "provision_target",
    "start_services",
    "readiness_check",
    "execute_tests",
    "teardown",
)

DEFAULT_HOOK_PHASES: dict[str, tuple[str, ...]] = {
    "pytest_configure": ("collect_inputs",),
    "pytest_sessionstart": (
        "setup_environment",
        "create_target",
        "declare_bootstrap_capabilities",
        "compose_bootstrap_capabilities",
        "flash_target",
        "start_target",
        "declare_runtime_capabilities",
        "compose_runtime_capabilities",
        "provision_target",
        "start_services",
        "readiness_check",
    ),
    "pytest_collection_modifyitems": (),
    "pytest_runtest_setup": (),
    "pytest_runtest_call": ("execute_tests",),
    "pytest_runtest_teardown": (),
    "pytest_sessionfinish": ("teardown",),
}


class ResultStatus(str, Enum):
    """Phase result status."""

    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"
    WARN = "warn"


@dataclass
class PhaseResult:
    """Plugin output for one phase."""

    plugin: str
    status: ResultStatus
    details: str = ""
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class PhaseDecision:
    """Resolver decision for one phase."""

    continue_workflow: bool = True
    reason: str = ""


@dataclass
class WorkflowContext:
    """Shared workflow state."""

    profile: dict[str, Any] = field(default_factory=dict)
    shared_resources: dict[str, Any] = field(default_factory=dict)
    capabilities: set[str] = field(default_factory=set)
    phase_results: dict[str, list[PhaseResult]] = field(default_factory=dict)
    events: list[str] = field(default_factory=list)


@dataclass
class WorkflowState:
    """Bridge cursor."""

    phases: tuple[str, ...]
    index: int = 0
    finished: bool = False


class WorkflowSpecs:
    """Pluggy hooks for the workflow bridge."""

    @hookspec(firstresult=True)
    def wf_get_phases(self) -> Sequence[str] | None:
        """Override the phase list."""

    @hookspec
    def wf_before_phase(self, ctx: WorkflowContext, phase: str) -> None:
        """Run before a phase."""

    @hookspec
    def wf_execute_phase(self, ctx: WorkflowContext, phase: str) -> PhaseResult | None:
        """Contribute work for a phase."""

    @hookspec
    def wf_after_phase(self, ctx: WorkflowContext, phase: str, results: list[PhaseResult]) -> None:
        """Run after a phase executes."""

    @hookspec(firstresult=True)
    def wf_resolve_phase(
        self,
        ctx: WorkflowContext,
        phase: str,
        results: list[PhaseResult],
    ) -> PhaseDecision | None:
        """Resolve a phase."""

    @hookspec
    def wf_on_error(self, ctx: WorkflowContext, phase: str, error: Exception) -> None:
        """Handle a phase error."""

    @hookspec
    def wf_finalize(self, ctx: WorkflowContext) -> None:
        """Finalize the bridge."""


class WorkflowBridge:
    """Drive workflow phases between pytest hook calls."""

    def __init__(self) -> None:
        self.pm = pluggy.PluginManager(PROJECT_NAME)
        self.pm.add_hookspecs(WorkflowSpecs)
        self.state: WorkflowState | None = None

    def register(self, plugin: object, name: str | None = None) -> None:
        """Register a plugin."""
        self.pm.register(plugin, name=name)

    def unregister(self, plugin: object | None = None, name: str | None = None) -> Any:
        """Unregister a plugin."""
        return self.pm.unregister(plugin=plugin, name=name)

    def phases(self) -> Sequence[str]:
        """Return the phase list."""
        phase_override = self.pm.hook.wf_get_phases()
        return tuple(phase_override) if phase_override else DEFAULT_PHASES

    def hook_phases(self, hook_name: str) -> tuple[str, ...]:
        """Return phases for one pytest hook."""
        return DEFAULT_HOOK_PHASES.get(hook_name, ())

    def begin(self, ctx: WorkflowContext | None = None) -> WorkflowContext:
        """Start a workflow session."""
        context = ctx or WorkflowContext()
        self.state = WorkflowState(phases=tuple(self.phases()))
        context.events.append("workflow:begin")
        return context

    def step(self, ctx: WorkflowContext, phase: str | None = None) -> bool:
        """Run one phase and resolve it."""
        state = self._require_state()
        if state.finished:
            return False

        current_phase = phase or self._next_phase()
        if current_phase is None:
            state.finished = True
            return False

        ctx.events.append(f"start:{current_phase}")
        self.pm.hook.wf_before_phase(ctx=ctx, phase=current_phase)

        raw_results = self.pm.hook.wf_execute_phase(ctx=ctx, phase=current_phase)
        phase_results = [result for result in raw_results if result is not None]
        ctx.phase_results[current_phase] = phase_results

        self.pm.hook.wf_after_phase(ctx=ctx, phase=current_phase, results=phase_results)

        decision = self.pm.hook.wf_resolve_phase(ctx=ctx, phase=current_phase, results=phase_results)
        if decision is not None and not decision.continue_workflow:
            reason = decision.reason or "resolver requested stop"
            ctx.events.append(f"stop:{current_phase}:{reason}")
            state.finished = True
            return False

        ctx.events.append(f"done:{current_phase}")
        return state.index < len(state.phases)

    def advance_hook(self, ctx: WorkflowContext, hook_name: str) -> bool:
        """Advance all phases mapped to one pytest hook."""
        hook_phases = self.hook_phases(hook_name)
        if not hook_phases:
            ctx.events.append(f"hook:{hook_name}:no-op")
            return True

        for phase in hook_phases:
            should_continue = self.step(ctx, phase=phase)
            if not should_continue:
                return False
        return True

    def finish(self, ctx: WorkflowContext) -> None:
        """Finalize the workflow bridge."""
        try:
            self.pm.hook.wf_finalize(ctx=ctx)
        finally:
            ctx.events.append("workflow:finish")
            self.state = None

    def run(self, ctx: WorkflowContext | None = None) -> WorkflowContext:
        """Run the whole workflow."""
        context = self.begin(ctx)

        try:
            while self.step(context):
                continue
        except Exception as exc:  # pragma: no cover - playground error path
            context.events.append(f"error:{exc}")
            self.pm.hook.wf_on_error(ctx=context, phase=self._phase_or_unknown(), error=exc)
            raise
        finally:
            self.finish(context)

        return context

    def _require_state(self) -> WorkflowState:
        if self.state is None:
            self.state = WorkflowState(phases=tuple(self.phases()))
        return self.state

    def _next_phase(self) -> str | None:
        state = self._require_state()
        if state.index >= len(state.phases):
            state.finished = True
            return None

        phase = state.phases[state.index]
        state.index += 1
        return phase

    def _phase_or_unknown(self) -> str:
        state = self.state
        if state is None or state.index == 0:
            return "unknown"
        previous_index = min(state.index - 1, len(state.phases) - 1)
        return state.phases[previous_index]


class TracePlugin:
    """Trace plugin example."""

    @hookimpl
    def wf_before_phase(self, ctx: WorkflowContext, phase: str) -> None:
        ctx.events.append(f"trace:before:{phase}")

    @hookimpl
    def wf_execute_phase(self, ctx: WorkflowContext, phase: str) -> PhaseResult:
        return PhaseResult(plugin="trace", status=ResultStatus.PASS, details=f"handled {phase}")

    @hookimpl
    def wf_after_phase(self, ctx: WorkflowContext, phase: str, results: list[PhaseResult]) -> None:
        ctx.events.append(f"trace:after:{phase}:{len(results)}")

    @hookimpl
    def wf_finalize(self, ctx: WorkflowContext) -> None:
        ctx.events.append("trace:finalize")


class StopOnFailureResolver:
    """Stop on first failure."""

    @hookimpl
    def wf_resolve_phase(
        self,
        ctx: WorkflowContext,
        phase: str,
        results: list[PhaseResult],
    ) -> PhaseDecision | None:
        for result in results:
            if result.status == ResultStatus.FAIL:
                return PhaseDecision(continue_workflow=False, reason=f"{result.plugin} failed")
        return None


def build_playground_runner() -> WorkflowBridge:
    """Build a ready-to-wire bridge."""
    bridge = WorkflowBridge()
    bridge.register(TracePlugin(), name="trace")
    bridge.register(StopOnFailureResolver(), name="stop_on_failure")
    return bridge
