"""Pytest integration: piggyback pytest's own lifecycle hooks.

Pytest is the execution host, and the engine does not invent a parallel phase
driver -- it *rides* pytest's real hooks:

    pytest_sessionstart      -> ctf_provision (FANOUT) + ctf_session_setup
    pytest_runtest_setup     -> ctf_before_test
    pytest_runtest_makereport-> ctf_collect (on the call phase)
    pytest_runtest_teardown  -> ctf_after_test (reverse)
    pytest_sessionfinish     -> ctf_session_teardown (reverse) + exit session

Two decoupled contribution hooks mirror the two planes:

    pytest_ctf_setup(registry, config)  -- composition plane (WHAT)
    pytest_ctf_steps(steps, config)     -- lifecycle plane   (WHEN)
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from ctf.diagnostics import format_composition_error, format_internal_error
from ctf.dut import DUT, build_manager
from ctf.errors import CompositionError, StepExecutionError
from ctf.registry import Registry
from ctf.assembly import Assembly
from ctf.steps import ArtifactSink, StepContext, StepRegistry

_KERNEL_ATTR = "_ctf_kernel"


# --------------------------------------------------------------------------
# Hook specifications (contribution points)
# --------------------------------------------------------------------------
class CtfHookSpecs:
    @pytest.hookspec
    def pytest_ctf_setup(self, registry: Registry, config: pytest.Config) -> None:
        """Populate the composition ``registry`` with targets and providers."""

    @pytest.hookspec
    def pytest_ctf_steps(self, steps: StepRegistry, config: pytest.Config) -> None:
        """Contribute lifecycle steps to extension points."""


def pytest_addhooks(pluginmanager: pytest.PytestPluginManager) -> None:
    pluginmanager.add_hookspecs(CtfHookSpecs)


# --------------------------------------------------------------------------
# Kernel: the session-lived composition + lifecycle owner
# --------------------------------------------------------------------------
@dataclass
class Kernel:
    registry: Registry
    steps: StepRegistry
    assembly: Assembly
    dut: DUT
    artifacts: ArtifactSink

    def context(self, **kwargs) -> StepContext:
        return StepContext(
            dut=self.dut,
            registry=self.registry,
            artifacts=self.artifacts,
            **kwargs,
        )


def _kernel(config: pytest.Config) -> "Kernel | None":
    return getattr(config, _KERNEL_ATTR, None)


def get_dut(config: pytest.Config) -> "DUT | None":
    """Public accessor: the composed :class:`DUT` for this session.

    Returns ``None`` when CTF is inactive. Lets plugins query the composition
    graph (e.g. ``dut.can_provide(contract)``) from pytest hooks without
    reaching into private kernel state.
    """
    kernel = _kernel(config)
    return kernel.dut if kernel is not None else None


# --------------------------------------------------------------------------
# Piggybacked pytest lifecycle hooks
# --------------------------------------------------------------------------
def pytest_sessionstart(session: pytest.Session) -> None:
    try:
        _compose_session(session)
    except CompositionError as exc:
        # The ecosystem is misconfigured. Stop the run cleanly with a sourced
        # diagnostic instead of an INTERNALERROR traceback.
        raise pytest.UsageError(format_composition_error(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - deliberate top-level boundary
        # A fault inside CTF itself. Still stop cleanly, but label it as our bug.
        raise pytest.UsageError(format_internal_error(exc)) from exc


def _compose_session(session: pytest.Session) -> None:
    """Assemble the kernel. Any failure here aborts the run (before tests)."""
    config = session.config
    registry = Registry()
    config.hook.pytest_ctf_setup(registry=registry, config=config)

    steps = StepRegistry()
    config.hook.pytest_ctf_steps(steps=steps, config=config)
    steps.validate()  # fail fast on UNIQUE collisions across all points

    manager = build_manager(registry)
    manager.enter()
    kernel = Kernel(registry, steps, manager, DUT(manager), ArtifactSink())
    try:
        ctx = kernel.context(config=config, session=session)
        _run_setup_step(kernel, "ctf_provision", ctx)  # FANOUT: every provisioner
        _run_setup_step(kernel, "ctf_session_setup", ctx)
    except BaseException:
        # Unwind the session we just entered so a partial start doesn't leak
        # resources when the boundary aborts the run.
        if manager.is_active:
            manager.exit()
        raise
    # Only publish the kernel once fully initialized.
    setattr(config, _KERNEL_ATTR, kernel)


def _run_setup_step(kernel: "Kernel", point: str, ctx: StepContext) -> None:
    """Resolve a session-setup point, attributing plugin faults to the plugin.

    Structural problems (``CompositionError``) propagate unchanged. A plugin
    step raising its own exception is wrapped as :class:`StepExecutionError` so
    it is reported as *that plugin's* fault, not as a framework bug.
    """
    try:
        kernel.steps.resolve(point, ctx)
    except CompositionError:
        raise
    except Exception as exc:  # noqa: BLE001 - attribute to the contributing step
        step = next(iter(kernel.steps.steps_for(point)), None)
        raise StepExecutionError(point, step.name if step else "<unknown>", exc) from exc


def pytest_runtest_setup(item: pytest.Item) -> None:
    kernel = _kernel(item.config)
    if kernel is None:
        return
    kernel.steps.resolve(
        "ctf_before_test", kernel.context(config=item.config, item=item)
    )


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo):
    outcome = yield
    report = outcome.get_result()
    kernel = _kernel(item.config)
    if kernel is None or report.when != "call":
        return
    kernel.steps.resolve(
        "ctf_collect",
        kernel.context(config=item.config, item=item, report=report),
    )


def pytest_runtest_teardown(item: pytest.Item, nextitem: "pytest.Item | None") -> None:
    kernel = _kernel(item.config)
    if kernel is None:
        return
    kernel.steps.resolve(
        "ctf_after_test",
        kernel.context(config=item.config, item=item),
        reverse=True,
    )


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    kernel = _kernel(session.config)
    if kernel is None:
        return
    kernel.steps.resolve(
        "ctf_session_teardown",
        kernel.context(config=session.config, session=session),
        reverse=True,
    )
    if kernel.assembly.is_active:
        kernel.assembly.exit()


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------
@pytest.fixture
def dut(request: pytest.FixtureRequest) -> DUT:
    """The session's DUT (a view over all resolved resources)."""
    kernel = _kernel(request.config)
    if kernel is None:  # pragma: no cover - defensive
        pytest.skip("CTF kernel was not initialized")
    return kernel.dut


@pytest.fixture
def ctf_kernel(request: pytest.FixtureRequest) -> "Kernel":
    """Access to the kernel (artifacts, registry, steps) for assertions."""
    kernel = _kernel(request.config)
    if kernel is None:  # pragma: no cover - defensive
        pytest.skip("CTF kernel was not initialized")
    return kernel


__all__ = ["DUT", "Kernel", "dut", "ctf_kernel", "get_dut", "pytest_addhooks"]
