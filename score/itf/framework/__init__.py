"""ITF Framework v2 — minimal contract-based plugin orchestration.

Writing a plugin only needs three things from here::

    from score.itf.framework import plugin_contract, itf_hookimpl, OracleResult

    @plugin_contract(name="my.plugin", provides=["thing"], requires=["target"])
    class MyPlugin:
        @itf_hookimpl
        def session_start_target_create(self, context):
            context.target = MyTarget()

        @itf_hookimpl
        def session_start_readiness_check(self, context):
            return OracleResult.pass_check("thing_ready")
"""

from score.itf.framework.contract import PluginContract, plugin_contract
from score.itf.framework.verdict import OracleResult
from score.itf.framework.context import ItfContext
from score.itf.framework.hooks import ItfHooks, itf_hookimpl, HOOK_NAMESPACE
from score.itf.framework.orchestrator import (
    ItfSessionOrchestrator,
    run_itf_session_start,
)
from score.itf.framework.plugin_loader import PluginLoader, register_plugins

__all__ = [
    # The three things a plugin author needs
    "plugin_contract",
    "itf_hookimpl",
    "OracleResult",
    # Needed when wiring a runner
    "ItfContext",
    "ItfHooks",
    "HOOK_NAMESPACE",
    "run_itf_session_start",
    # Advanced / optional
    "PluginContract",
    "ItfSessionOrchestrator",
    "PluginLoader",
    "register_plugins",
]
