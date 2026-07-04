"""ITF session orchestrator with contract validation."""

from __future__ import annotations

import logging
from typing import Any

from score.itf.framework.contract import PluginContract
from score.itf.framework.context import ItfContext
from score.itf.framework.hooks import ItfHooks, STARTUP_PHASES, TEARDOWN_PHASES, HOOK_NAMESPACE
from score.itf.framework.verdict import OracleResult
import pluggy

logger = logging.getLogger(__name__)


class CompositionError(Exception):
    """Plugin composition validation error."""
    pass


class ItfSessionOrchestrator:
    """Orchestrates ITF session lifecycle with contract validation.

    Responsibilities:
    1. Validate plugin composition before startup
    2. Execute phases in order
    3. Collect readiness checks
    4. Manage cleanup
    """

    def __init__(self, pm: pluggy.PluginManager, context: ItfContext):
        """Initialize orchestrator.

        Args:
            pm: pluggy PluginManager
            context: ItfContext for coordination
        """
        self.pm = pm
        self.context = context
        self.plugins: list[tuple[str, Any]] = []
        self.readiness_results: list[Any] = []

    def discover_plugins(self) -> None:
        """Discover registered plugins and their contracts."""
        for plugin_name, plugin in self.pm.list_name_plugin():
            self.plugins.append((plugin_name, plugin))
            logger.debug(f"Discovered plugin: {plugin_name}")

    def validate_composition(self) -> None:
        """Validate plugin composition.

        Checks:
        1. Every plugin has a __contract__.
        2. All requires are satisfied by some plugin's provides.

        Raises:
            CompositionError: If composition is invalid.
        """
        contracts: list[PluginContract] = []
        provided_capabilities: set[str] = set()

        for plugin_name, plugin in self.plugins:
            if not hasattr(plugin, "__contract__"):
                raise CompositionError(
                    f"Plugin '{plugin_name}' has no __contract__. "
                    f"Add @plugin_contract(name=..., provides=[...], requires=[...])."
                )
            contract: PluginContract = plugin.__contract__
            contracts.append(contract)
            # Auto-detect which phases this plugin implements for logging.
            all_phases = set(STARTUP_PHASES) | set(TEARDOWN_PHASES)
            active = [p for p in all_phases if callable(getattr(plugin, p, None))]
            logger.debug(
                "Plugin %s: provides=%s requires=%s active_phases=%s",
                contract.name, contract.provides, contract.requires, sorted(active),
            )

        for contract in contracts:
            for req in contract.requires:
                if not any(req in other.provides for other in contracts):
                    raise CompositionError(
                        f"Plugin '{contract.name}' requires '{req}' "
                        f"but no loaded plugin provides it."
                    )
            for cap in contract.provides:
                provided_capabilities.add(cap)

        logger.info(
            "Composition valid: %d plugins, collective provides: %s",
            len(contracts), provided_capabilities,
        )

    def _normalize_check_results(self, result: Any) -> list[OracleResult]:
        """Normalize hook return values to OracleResult list."""
        if result is None:
            return []
        if isinstance(result, OracleResult):
            return [result]
        if isinstance(result, list):
            normalized: list[OracleResult] = []
            for item in result:
                normalized.extend(self._normalize_check_results(item))
            return normalized
        if isinstance(result, dict):
            return [
                OracleResult(
                    name=str(result.get("name", "check")),
                    passed=bool(result.get("passed", False)),
                    blocking=bool(result.get("blocking", False)),
                    details=str(result.get("details", "")),
                    metadata=dict(result.get("metadata", {})),
                )
            ]
        raise CompositionError(f"Unsupported readiness result type: {type(result)!r}")

    def execute_phase(self, phase_name: str) -> list[Any]:
        """Execute a single lifecycle phase.

        Calls every loaded plugin that implements `phase_name` as a method.
        No need to declare phases in the contract — auto-detected from methods.
        """
        logger.info("[PHASE] %s", phase_name)
        results: list[Any] = []
        for _plugin_name, plugin in self.plugins:
            hook = getattr(plugin, phase_name, None)
            if callable(hook):
                results.append(hook(self.context))
        return results

    def execute_startup(self) -> None:
        """Execute all startup phases.

        Raises:
            CompositionError: If validation fails
            RuntimeError: If any blocking readiness check fails
        """
        logger.info("=== Starting ITF Session ===")

        # Validate composition first
        self.validate_composition()

        # Execute startup phases
        for phase in STARTUP_PHASES:
            phase_results = self.execute_phase(phase)

            # After readiness checks, verify no blocking failures
            if phase == "session_start_readiness_check":
                for result in phase_results:
                    self.context.startup_checks.extend(self._normalize_check_results(result))
                blocking_failures = [
                    check for check in self.context.startup_checks
                    if hasattr(check, "blocking") and check.blocking and not check.passed
                ]
                if blocking_failures:
                    details = "; ".join(c.details for c in blocking_failures)
                    raise RuntimeError(
                        f"Blocking readiness checks failed: {details}"
                    )

    def execute_teardown(self) -> None:
        """Execute all teardown phases."""
        logger.info("=== Finishing ITF Session ===")

        # Execute teardown phases
        for phase in TEARDOWN_PHASES:
            try:
                self.execute_phase(phase)
            except Exception as exc:
                logger.error(f"Error in {phase}: {exc}", exc_info=True)

        # Run cleanup callbacks (reverse order)
        try:
            self.context.run_cleanup()
        except Exception as exc:
            logger.error(f"Error in cleanup callbacks: {exc}", exc_info=True)

        logger.info("=== ITF Session Finished ===")


def run_itf_session_start(pm: pluggy.PluginManager, context: ItfContext) -> None:
    """Run ITF session startup with orchestrator.

    Args:
        pm: pluggy PluginManager with registered plugins
        context: ItfContext for coordination

    Raises:
        CompositionError: If plugin composition is invalid
        RuntimeError: If startup fails
    """
    orchestrator = ItfSessionOrchestrator(pm, context)
    orchestrator.discover_plugins()
    orchestrator.execute_startup()
    context.metadata["orchestrator"] = orchestrator
