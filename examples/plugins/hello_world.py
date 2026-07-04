"""Example custom plugin showing how to extend ITF."""

from __future__ import annotations

import logging

from score.itf.framework import (
    plugin_contract,
    itf_hookimpl,
    OracleResult,
)

logger = logging.getLogger(__name__)


@plugin_contract(
    name="example.plugins.hello_world",
    provides=["greeting"],
    requires=[],
    writes=["shared_resources"],
    reads=[],
    phases=["session_start_environment_freeze"],
    readiness_checks=["hello_world_ready"],
    description="Simple example plugin that adds a greeting to shared resources",
)
class HelloWorldPlugin:
    """Example custom plugin demonstrating plugin development.

    This plugin:
    1. Declares a simple contract with one phase
    2. Adds a greeting message to shared resources
    3. Performs a readiness check

    To use this plugin, pass it to the runner:
        python -m score.itf.runner --plugins example.plugins.hello_world -- -v
    """

    @itf_hookimpl
    def session_start_environment_freeze(self, context):
        """Add greeting to shared resources when environment is frozen."""
        logger.info("HelloWorldPlugin: Adding greeting")

        message = "Hello, ITF World! 🎉"
        context.shared_resources["hello_message"] = message

        logger.info(f"Greeting stored: {message}")

    @itf_hookimpl
    def session_start_readiness_check(self, context):
        """Check that greeting is available."""
        logger.debug("HelloWorldPlugin: readiness check")

        message = context.shared_resources.get("hello_message")

        if message:
            return OracleResult.pass_check(
                name="hello_world_ready",
                details=f"Greeting ready: {message}",
            )
        else:
            return OracleResult.fail_check(
                name="hello_world_ready",
                details="Greeting not set",
                blocking=False,
            )
