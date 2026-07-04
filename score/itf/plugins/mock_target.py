"""Mock target plugin for testing."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from score.itf.framework import (
    plugin_contract,
    itf_hookimpl,
    OracleResult,
)

logger = logging.getLogger(__name__)


@dataclass
class MockTargetState:
    """State for mock target.

    Owned by: mock_target plugin
    Stored in: context.use_state(MockTargetState)
    """
    container_id: str = "mock-container-001"
    hostname: str = "mock-target"
    is_running: bool = False
    properties: dict[str, Any] = field(default_factory=dict)


class MockTarget:
    """Minimal mock target implementation."""

    def __init__(self, container_id: str, hostname: str):
        self.container_id = container_id
        self.hostname = hostname
        self.is_running = False
        self.capabilities: set[str] = set()

    def start(self) -> None:
        """Start the target."""
        self.is_running = True
        logger.info(f"Mock target started: {self.hostname}")

    def stop(self) -> None:
        """Stop the target."""
        self.is_running = False
        logger.info(f"Mock target stopped: {self.hostname}")

    def add_capability(self, name: str) -> None:
        """Add a capability to the target."""
        self.capabilities.add(name)

    def get_capabilities(self) -> set[str]:
        """Get available capabilities."""
        return self.capabilities.copy()


@plugin_contract(
    name="score.itf.plugins.mock_target",
    provides=["target"],
    description="Provides a mock target for testing without real hardware",
)
class MockTargetPlugin:
    """Mock target provider.

    Creates a simulated target that can have capabilities attached.
    This plugin provides the basic target interface without real container/hardware.
    """

    @itf_hookimpl
    def session_start_profile_resolve(self, context):
        """Resolve target profile from config."""
        logger.debug("MockTargetPlugin: resolving profile")

        # Initialize mock target state
        state = context.use_state(
            MockTargetState,
            owner="mock_target",
            factory=lambda: MockTargetState(
                container_id="mock-container-001",
                hostname="mock-target",
            ),
        )
        logger.info(f"Mock target profile: {state.hostname}")

    @itf_hookimpl
    def session_start_target_create(self, context):
        """Create the mock target."""
        logger.info("MockTargetPlugin: creating target")

        state = context.get_state(MockTargetState)
        if state is None:
            raise RuntimeError("MockTargetState not initialized")

        # Create mock target
        target = MockTarget(
            container_id=state.container_id,
            hostname=state.hostname,
        )

        # Store in context
        context.target = target
        state.is_running = False

        # Register cleanup
        def cleanup_target():
            if target.is_running:
                try:
                    target.stop()
                except Exception as exc:
                    logger.warning(f"Error stopping mock target: {exc}")

        context.add_cleanup_callback(cleanup_target)
        logger.info(f"Mock target created: {target.hostname}")

    @itf_hookimpl
    def session_start_target_prepare(self, context):
        """Prepare/start the mock target."""
        logger.info("MockTargetPlugin: preparing target")

        if context.target is None:
            logger.warning("No target to prepare")
            return

        # Start the mock target
        context.target.start()

        state = context.get_state(MockTargetState)
        if state:
            state.is_running = True

    @itf_hookimpl
    def session_start_readiness_check(self, context):
        """Check that mock target is ready."""
        logger.debug("MockTargetPlugin: readiness check")

        if context.target is None:
            return OracleResult.fail_check(
                name="mock_target_ready",
                details="Target not created",
                blocking=True,
            )

        if not context.target.is_running:
            return OracleResult.fail_check(
                name="mock_target_ready",
                details="Target not running",
                blocking=True,
            )

        return OracleResult.pass_check(
            name="mock_target_ready",
            details=f"Mock target ready: {context.target.hostname}",
        )
