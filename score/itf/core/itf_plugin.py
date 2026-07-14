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
"""ITF pytest plugin: integrates the Composable Target Framework with pytest.

This is the entry point plugin that test projects import in their conftest::

    pytest_plugins = ["score.itf.core.itf_plugin"]

It exposes CTF's composition engine through pytest's lifecycle via phased hooks.
Each phase name is a **verb** describing what happens during that phase:

    pytest_itf_declare(registry, config)     — Declare targets, descriptors,
                                               providers. Build the DUT graph.
    pytest_itf_init(dut, config)             — Initialize hardware: power up,
                                               flash, signal init.
    pytest_itf_provision(dut, config)        — Provision the target: start
                                               container, deploy tokens, start
                                               env simulation.
    pytest_itf_verify(dut, config)           — Verify readiness: startup checks,
                                               sanity tests. Plugins contribute
                                               their own checks.
    pytest_itf_teardown(dut, config)         — Session-level teardown before
                                               assembly destruction.

The DUT is shared via pytest session and accessible through the ``dut`` fixture
or programmatically via ``get_dut(config)``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import pytest

from score.itf.core.ctf.assembly import Assembly
from score.itf.core.ctf.diagnostics import format_composition_error, format_internal_error
from score.itf.core.ctf.dut import DUT, build_device_assemblies, build_manager
from score.itf.core.ctf.errors import CompositionError
from score.itf.core.ctf.registry import Registry
from score.itf.core.ctf.contracts import provides
from score.itf.core.ctf.target import TARGET_ANCHOR, is_anchor

logger = logging.getLogger(__name__)


def _emit_phase(log: logging.Logger, title: str) -> None:
    """Emit a phase-marker log record.

    The logger plugin's formatter detects the ``_itf_section`` attribute and
    renders it as a visual section separator. Without the logger plugin, this
    is just a normal INFO message.
    """
    record = log.makeRecord(log.name, logging.INFO, "(itf)", 0, title, args=(), exc_info=None)
    record._itf_section = title  # type: ignore[attr-defined]
    log.handle(record)


def _reject_hookwrappers(impls, hook_name: str) -> None:
    """Raise if any hookimpl uses hookwrapper on a manually-iterated hook."""
    for impl in impls:
        if impl.hookwrapper or getattr(impl, "wrapper", False):
            raise pytest.UsageError(
                f"hookwrapper is not supported on {hook_name} — "
                f"found on {impl.function.__module__}.{impl.function.__qualname__}"
            )


def _log_registry(registry: Registry) -> None:
    """Log declared providers and descriptors."""
    for provider in registry.providers():
        deps = ", ".join(provider.requires) if provider.requires else "(none)"
        logger.info("  [provider] %s ← %s  (%s)", provider.provides, deps, provider.name)
    for contract in sorted(registry.contracts() - frozenset(p.provides for p in registry.providers())):
        desc = registry.descriptor(contract)
        if desc is not None:
            logger.info("  [descriptor] %s = %r", contract, desc.value)
    # Log device registries
    for name in sorted(registry.device_names()):
        dev_reg = registry.device_registry(name)
        if dev_reg is not None:
            logger.info("")
            logger.info("  ┌─ Device: %s", name)
            for provider in dev_reg.providers():
                deps = ", ".join(provider.requires) if provider.requires else "(none)"
                logger.info("  │  [provider] %s ← %s  (%s)", provider.provides, deps, provider.name)
            for contract in sorted(dev_reg.local_contracts() - frozenset(p.provides for p in dev_reg.providers())):
                desc = dev_reg.descriptor(contract)
                if desc is not None:
                    logger.info("  │  [descriptor] %s = %r", contract, desc.value)
            logger.info("  └%s", "─" * 40)


def _log_aliases(dut: DUT) -> None:
    """Log registered aliases."""
    for alias, contract in dut.aliases().items():
        logger.info("  %s -> %s", alias, contract)


def _log_graph(dut: DUT, config: "pytest.Config") -> None:
    """Log the resolved composition graph grouped by tier."""
    kernel = _kernel(config)
    if kernel is None:
        return

    plan = kernel.assembly.plan
    registry = kernel.registry

    # Group contracts by tier
    tier_groups: dict[int, list[str]] = {}
    for contract, tier in sorted(plan.tier_of.items(), key=lambda x: (x[1], x[0])):
        tier_groups.setdefault(tier, []).append(contract)

    logger.info("Mode: %s", plan.mode.value)
    logger.info("Spine: %d contracts", len(plan.spine))
    logger.info("Available: %d contracts", len(plan.available))
    if plan.unavailable:
        logger.info("Unavailable: %d contracts", len(plan.unavailable))
    logger.info("")

    for tier_num in sorted(tier_groups):
        contracts = tier_groups[tier_num]
        logger.info("  ┌─ Tier %d (%d nodes)", tier_num, len(contracts))
        for contract in contracts:
            provider = registry.provider(contract)
            descriptor = registry.descriptor(contract)
            in_spine = "●" if contract in plan.spine else "○"
            if descriptor is not None:
                logger.info("  │  %s %s [descriptor]", in_spine, contract)
            elif provider is not None:
                deps = ", ".join(provider.requires) if provider.requires else "—"
                logger.info("  │  %s %s ← requires(%s)", in_spine, contract, deps)
            else:
                logger.info("  │  %s %s", in_spine, contract)
        logger.info("  └%s", "─" * 40)

    if plan.unavailable:
        logger.info("")
        logger.info("  Unavailable capabilities:")
        for contract, reason in sorted(plan.unavailable.items()):
            logger.info("    ✕ %s: %s", contract, reason)

    # Log device assembly graphs
    for name in sorted(kernel.registry.device_names()):
        proxy = kernel.dut._devices.get(name)
        if proxy is None:
            continue
        dev_plan = proxy._assembly.plan
        dev_registry = proxy._assembly.registry
        logger.info("")
        logger.info("  ╔═ Device: %s (%d available)", name, len(dev_plan.available))
        dev_tier_groups: dict[int, list[str]] = {}
        for contract, tier in sorted(dev_plan.tier_of.items(), key=lambda x: (x[1], x[0])):
            dev_tier_groups.setdefault(tier, []).append(contract)
        for tier_num in sorted(dev_tier_groups):
            contracts = dev_tier_groups[tier_num]
            logger.info("  ║  ┌─ Tier %d (%d nodes)", tier_num, len(contracts))
            for contract in contracts:
                provider = dev_registry.provider(contract)
                descriptor = dev_registry.descriptor(contract)
                in_spine = "●" if contract in dev_plan.spine else "○"
                if descriptor is not None:
                    logger.info("  ║  │  %s %s [descriptor]", in_spine, contract)
                elif provider is not None:
                    deps = ", ".join(provider.requires) if provider.requires else "—"
                    logger.info("  ║  │  %s %s ← requires(%s)", in_spine, contract, deps)
                else:
                    logger.info("  ║  │  %s %s", in_spine, contract)
            logger.info("  ║  └%s", "─" * 36)
        if dev_plan.unavailable:
            for contract, reason in sorted(dev_plan.unavailable.items()):
                logger.info("  ║  ✕ %s: %s", contract, reason)
        logger.info("  ╚%s", "═" * 40)


_KERNEL_ATTR = "_itf_kernel"
_STARTUP_CHECKS_ATTR = "_itf_startup_checks"


# --------------------------------------------------------------------------
# Startup check reporting (used by verify hooks)
# --------------------------------------------------------------------------
@dataclass
class StartupCheck:
    """Result of a single startup verification check."""

    name: str
    status: str  # "passed" | "failed" | "skipped"
    duration: float = 0.0
    detail: str = ""


def report_startup_check(
    config: pytest.Config,
    name: str,
    status: str = "passed",
    duration: float = 0.0,
    detail: str = "",
) -> None:
    """Report a startup check result during the verify phase.

    Plugins call this from their ``pytest_itf_verify`` implementation to
    register individual check results that show up in the dashboard as a
    startup test suite.
    """
    checks: list[StartupCheck] = getattr(config, _STARTUP_CHECKS_ATTR, [])
    checks.append(StartupCheck(name=name, status=status, duration=duration, detail=detail))
    setattr(config, _STARTUP_CHECKS_ATTR, checks)


def get_startup_checks(config: pytest.Config) -> list[StartupCheck]:
    """Public accessor: startup check results from the verify phase."""
    return getattr(config, _STARTUP_CHECKS_ATTR, [])


# --------------------------------------------------------------------------
# Hook specifications (contribution points for plugins)
# --------------------------------------------------------------------------
class ItfHookSpecs:
    """Phased lifecycle hooks for ITF plugins.

    Each phase is a verb describing the action performed. Plugins implement
    whichever phases they need.
    """

    @pytest.hookspec
    def pytest_itf_declare(self, registry: Registry, config: pytest.Config) -> None:
        """Declare descriptors and providers — build the composition graph.

        This is where plugins register their targets, capabilities, and facts.
        No side effects should happen here — only graph construction.
        """

    @pytest.hookspec(firstresult=False)
    def pytest_itf_init(self, dut: DUT, config: pytest.Config) -> None:
        """Initialize the environment: power up hardware, init flasher, signals.

        The DUT graph is resolved but the target may not be running yet.
        This phase handles low-level hardware bring-up.
        """

    @pytest.hookspec(firstresult=False)
    def pytest_itf_provision(self, dut: DUT, config: pytest.Config) -> None:
        """Provision the target: start container, deploy credentials, start services.

        After this phase the target should be primed and usable.
        """

    @pytest.hookspec(firstresult=False)
    def pytest_itf_verify(self, dut: DUT, config: pytest.Config) -> None:
        """Verify target readiness: startup checks, sanity pings.

        Each plugin contributes its own verification logic. If any check
        fails the session aborts. Results are reported as a startup
        test suite in the eventual report.
        """

    @pytest.hookspec(firstresult=False)
    def pytest_itf_aliases(self, dut: DUT, config: pytest.Config) -> None:
        """Register short aliases for contract strings.

        Called after DECLARE (graph is resolved) but before INIT. Conftests
        and plugins register aliases so test code uses project-level names::

            @pytest.hookimpl
            def pytest_itf_aliases(dut, config):
                dut.alias("shell", "itf/cap/exec")
                dut.alias("files", "itf/cap/file_transfer")
                dut.alias("target", "ctf/target")
        """

    @pytest.hookspec(firstresult=False)
    def pytest_itf_bindings(self, registry: Registry, config: pytest.Config) -> None:
        """Redirect provider requirements (contract bindings).

        Called after DECLARE but before graph resolution. Allows the root
        conftest to remap what contract a provider receives for one of its
        declared requirements — enabling generic plugins to work with
        project-specific contracts::

            @pytest.hookimpl
            def pytest_itf_bindings(registry, config):
                # UDP heartbeat should use the heartbeat IP, not the main one
                registry.bind("itf/cap/udp_heartbeat",
                              "itf/net/ip_address", "itf/net/heartbeat_ip")
        """

    @pytest.hookspec(firstresult=False)
    def pytest_itf_teardown(self, dut: DUT, config: pytest.Config) -> None:
        """Session-level teardown before the assembly is destroyed."""


def pytest_addhooks(pluginmanager: pytest.PytestPluginManager) -> None:
    pluginmanager.add_hookspecs(ItfHookSpecs)


# --------------------------------------------------------------------------
# Kernel: the session-lived composition + lifecycle owner
# --------------------------------------------------------------------------
@dataclass
class Kernel:
    registry: Registry
    assembly: Assembly
    dut: DUT


def _kernel(config: pytest.Config) -> "Kernel | None":
    return getattr(config, _KERNEL_ATTR, None)


def get_dut(config: pytest.Config) -> "DUT | None":
    """Public accessor: the composed :class:`DUT` for this session.

    Returns ``None`` when ITF is inactive. Lets plugins query the composition
    graph from pytest hooks without reaching into private kernel state.
    """
    kernel = _kernel(config)
    return kernel.dut if kernel is not None else None


# --------------------------------------------------------------------------
# Fallback: provide a skip-producing anchor when no target plugin is loaded
# --------------------------------------------------------------------------
@pytest.hookimpl(trylast=True)
def pytest_itf_declare(registry, config):
    """Register a fallback anchor only when no target plugin contributes one."""
    has_any_anchor = any(is_anchor(c) for c in registry.contracts())
    if has_any_anchor:
        return

    @provides(TARGET_ANCHOR)
    def _no_target():
        pytest.skip("No target plugin loaded; cannot resolve ctf/target")

    registry.register(_no_target)


# --------------------------------------------------------------------------
# Piggybacked pytest lifecycle hooks
# --------------------------------------------------------------------------
def pytest_sessionstart(session: pytest.Session) -> None:
    try:
        _compose_session(session)
    except CompositionError as exc:
        raise pytest.UsageError(format_composition_error(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - deliberate top-level boundary
        raise pytest.UsageError(format_internal_error(exc)) from exc


def _compose_session(session: pytest.Session) -> None:
    """Assemble the kernel and run phased lifecycle."""
    config = session.config
    registry = Registry()

    # Phase 1: DECLARE — build the composition graph
    _emit_phase(logger, "DECLARE — Graph Construction")
    config.hook.pytest_itf_declare(registry=registry, config=config)
    _log_registry(registry)

    # Phase 1.5: BINDINGS — redirect provider requirements (root conftest only)
    _emit_phase(logger, "BINDINGS — Requirement Redirects")
    _run_bindings_phase(registry=registry, config=config)
    registry.apply_bindings()

    # Resolve and enter the assemblies (root + per-device)
    assembly = build_manager(registry)
    device_assemblies = build_device_assemblies(registry)
    assembly.enter()
    for dev_asm in device_assemblies.values():
        dev_asm.enter()
    dut = DUT(assembly, device_assemblies)
    kernel = Kernel(registry, assembly, dut)
    setattr(config, _KERNEL_ATTR, kernel)

    try:
        # Phase 1.5: ALIASES — register project-level names (root conftest only)
        _emit_phase(logger, "ALIASES — Domain Vocabulary")
        _run_aliases_phase(dut=dut, config=config)
        dut.lock_aliases()
        _log_aliases(dut)

        # Composition graph (frozen at this point)
        _emit_phase(logger, "COMPOSITION GRAPH — Resolved")
        _log_graph(dut, config)

        # Phase 2: INIT — Target bring-up
        _emit_phase(logger, "INIT — Target Bring-Up")
        config.hook.pytest_itf_init(dut=dut, config=config)

        # Phase 3: PROVISION — prepare the target
        _emit_phase(logger, "PROVISION — Target Deployment")
        config.hook.pytest_itf_provision(dut=dut, config=config)

        # Phase 4: VERIFY — startup checks (auto-reported per plugin)
        _run_verify_phase(dut=dut, config=config)
    except BaseException:
        for dev_asm in reversed(list(device_assemblies.values())):
            if dev_asm.is_active:
                dev_asm.exit()
        if assembly.is_active:
            assembly.exit()
        raise


def _find_top_conftest_dirs(impls) -> "frozenset[pathlib.Path]":
    """Find all highest-level (shallowest) conftest directories among hookimpls.

    Multiple independent roots may contribute conftests at the same depth
    (for example, two example suites under ``examples/*``). All shallowest
    conftests are treated as top-level and allowed to participate.
    """
    import pathlib

    candidates: list[pathlib.Path] = []
    for impl in impls:
        if not _is_conftest_module(impl.function.__module__, impl):
            continue
        source_file = _get_source_file(impl)
        if source_file is not None:
            candidates.append(pathlib.Path(source_file).parent)

    if not candidates:
        return frozenset()

    min_depth = min(len(p.parts) for p in candidates)
    return frozenset(p for p in candidates if len(p.parts) == min_depth)


def _run_aliases_phase(dut: DUT, config: pytest.Config) -> None:
    """Run alias hooks — only from the top-level conftest or installed plugins.

    Only the highest-level (shallowest) conftest directories are allowed to
    register aliases.
    Sub-directory conftests are excluded because aliases define project-wide
    vocabulary. This prevents per-directory alias drift.
    """
    import pathlib

    hook_caller = config.hook.pytest_itf_aliases
    impls = hook_caller.get_hookimpls()
    _reject_hookwrappers(impls, "pytest_itf_aliases")
    top_conftest_dirs = _find_top_conftest_dirs(impls)

    for impl in reversed(impls):
        module = impl.function.__module__
        # Installed plugins (score.itf.*, third-party) — always allowed
        if module != "conftest" and not _is_conftest_module(module, impl):
            impl.function(dut=dut, config=config)
            continue

        # conftest modules: only allow top-level
        source_file = _get_source_file(impl)
        if source_file is None:
            # Can't determine source — allow (benefit of the doubt)
            impl.function(dut=dut, config=config)
            continue

        conftest_dir = pathlib.Path(source_file).parent
        if not top_conftest_dirs or conftest_dir in top_conftest_dirs:
            impl.function(dut=dut, config=config)
        else:
            logger.warning(
                "Ignoring pytest_itf_aliases from sub-conftest %s — "
                "aliases must be registered in a top-level conftest (%s)",
                source_file,
                ", ".join(f"{path}/conftest.py" for path in sorted(top_conftest_dirs)),
            )


def _is_conftest_module(module_name: str, impl) -> bool:
    """Check if a hookimpl comes from a conftest file."""
    if module_name == "conftest":
        return True
    source = _get_source_file(impl)
    if source and "conftest" in source:
        return True
    return False


def _get_source_file(impl) -> "str | None":
    """Get the source file path of a hookimpl."""
    import inspect

    try:
        return inspect.getfile(impl.function)
    except (TypeError, OSError):
        return None


def _run_bindings_phase(registry: Registry, config: pytest.Config) -> None:
    """Run binding hooks — only from the top-level conftest or installed plugins.

    Same restriction as aliases: sub-directory conftests are excluded.
    Bindings must run before assembly construction because they modify the
    provider dependency graph.
    """
    import pathlib

    hook_caller = config.hook.pytest_itf_bindings
    impls = hook_caller.get_hookimpls()
    _reject_hookwrappers(impls, "pytest_itf_bindings")
    top_conftest_dirs = _find_top_conftest_dirs(impls)

    for impl in reversed(impls):
        module = impl.function.__module__
        # Installed plugins — always allowed
        if module != "conftest" and not _is_conftest_module(module, impl):
            impl.function(registry=registry, config=config)
            continue

        # conftest modules: only allow top-level
        source_file = _get_source_file(impl)
        if source_file is None:
            impl.function(registry=registry, config=config)
            continue

        conftest_dir = pathlib.Path(source_file).parent
        if not top_conftest_dirs or conftest_dir in top_conftest_dirs:
            impl.function(registry=registry, config=config)
        else:
            logger.warning(
                "Ignoring pytest_itf_bindings from sub-conftest %s — "
                "bindings must be registered in a top-level conftest (%s)",
                source_file,
                ", ".join(f"{path}/conftest.py" for path in sorted(top_conftest_dirs)),
            )


def _run_verify_phase(dut: DUT, config: pytest.Config) -> None:
    """Run verify hooks one-by-one, auto-reporting each as a startup check.

    Failure semantics depend on the hook source:
    - **Conftest** hooks always fail-fast (abort session) — they represent
      project-specific invariants the user explicitly cares about.
    - **Plugin** hooks respect the assembly run mode:
      - STRICT → fail-fast (same as conftest)
      - LOOSE → log warning and continue (non-essential plugin internals
        should not block the run unless the user opts in)
    """
    import time as _time
    from score.itf.core.ctf.assembly import RunMode

    hook_caller = config.hook.pytest_itf_verify
    impls = hook_caller.get_hookimpls()
    _reject_hookwrappers(impls, "pytest_itf_verify")

    kernel = _kernel(config)
    mode = kernel.assembly.mode if kernel else RunMode.STRICT

    # Emit phase marker (rendered as section header by the logger formatter)
    _emit_phase(logger, "VERIFY — Startup Checks")

    for impl in reversed(impls):
        # Derive a human-readable check name from the plugin module
        module = impl.function.__module__
        parts = module.split(".")
        if "plugin" in parts:
            parts.remove("plugin")
        check_name = parts[-1] if parts else module

        is_conftest = _is_conftest_module(module, impl)

        _emit_phase(logger, f"CHECK — {check_name}")
        t0 = _time.time()
        try:
            impl.function(dut=dut, config=config)
            duration = _time.time() - t0
            logger.info("Result: PASSED (%.3fs)", duration)
            _auto_report_if_needed(config, check_name, "passed", duration)
        except Exception as exc:
            duration = _time.time() - t0
            logger.info("Result: FAILED (%.3fs) — %s", duration, exc)
            _auto_report_if_needed(config, check_name, "failed", duration, detail=str(exc))

            if is_conftest or mode is RunMode.STRICT:
                raise
            else:
                logger.warning(
                    "Verify hook '%s' (from %s) failed but mode is LOOSE — continuing. Error: %s",
                    check_name,
                    module,
                    exc,
                )

    # Summary
    checks = get_startup_checks(config)
    if checks:
        passed = sum(1 for c in checks if c.status == "passed")
        failed = sum(1 for c in checks if c.status == "failed")
        skipped = sum(1 for c in checks if c.status == "skipped")
        total = len(checks)
        summary_parts = []
        if passed:
            summary_parts.append(f"{passed} passed")
        if failed:
            summary_parts.append(f"{failed} failed")
        if skipped:
            summary_parts.append(f"{skipped} skipped")
        _emit_phase(logger, f"VERIFY SUMMARY — {', '.join(summary_parts)} ({total} total)")


def _auto_report_if_needed(
    config: pytest.Config,
    check_name: str,
    status: str,
    duration: float,
    detail: str = "",
) -> None:
    """Auto-report a startup check unless the plugin already reported one with this prefix."""
    checks: list[StartupCheck] = getattr(config, _STARTUP_CHECKS_ATTR, [])
    # If any check already starts with this name, the plugin is self-reporting
    already_reported = any(c.name.startswith(check_name + "/") or c.name == check_name for c in checks)
    if not already_reported:
        report_startup_check(config, check_name, status, duration, detail)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    kernel = _kernel(session.config)
    if kernel is None:
        return
    _emit_phase(logger, "TEARDOWN — Reverse-Order Destruction")
    session.config.hook.pytest_itf_teardown(dut=kernel.dut, config=session.config)
    # Tear down device assemblies first (reverse of enter order)
    for name in reversed(sorted(kernel.registry.device_names())):
        dev_reg = kernel.registry.device_registry(name)
        if dev_reg is not None:
            # Device assemblies are accessed through the DUT's device proxies
            proxy = kernel.dut._devices.get(name)
            if proxy and proxy._assembly.is_active:
                proxy._assembly.exit()
    if kernel.assembly.is_active:
        kernel.assembly.exit()


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------
@pytest.fixture
def dut(request: pytest.FixtureRequest) -> DUT:
    """The session's DUT (a view over all resolved resources).

    Shared via pytest session — native pytest hooks can access it.
    """
    kernel = _kernel(request.config)
    if kernel is None:
        pytest.skip("ITF kernel was not initialized")
    return kernel.dut


@pytest.fixture
def itf_kernel(request: pytest.FixtureRequest) -> "Kernel":
    """Access to the kernel (registry, assembly, dut) for assertions."""
    kernel = _kernel(request.config)
    if kernel is None:
        pytest.skip("ITF kernel was not initialized")
    return kernel


__all__ = [
    "DUT",
    "Kernel",
    "StartupCheck",
    "dut",
    "itf_kernel",
    "get_dut",
    "get_startup_checks",
    "report_startup_check",
    "pytest_addhooks",
]
