"""Mock SSH capability plugin."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from score.itf.framework import (
    plugin_contract,
    itf_hookimpl,
    OracleResult,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MockSshEndpointState:
    """SSH endpoint configuration.

    Owned by: mock_ssh plugin
    Stored in: context.use_state(MockSshEndpointState)
    """
    host: str = "127.0.0.1"
    port: int = 22
    username: str = "root"


class SimpleMockSshExecutor:
    """Simple mock SSH executor (doesn't actually connect)."""

    def __init__(self, host: str, port: int, username: str):
        self.host = host
        self.port = port
        self.username = username

    def run_command(self, cmd: str) -> tuple[int, str, str]:
        """Mock command execution."""
        logger.debug(f"[MOCK SSH] {self.username}@{self.host}: {cmd}")
        # Mock success for all commands
        return 0, f"[MOCK OUTPUT]: {cmd}", ""


@plugin_contract(
    name="score.itf.plugins.mock_ssh",
    provides=["ssh_endpoint", "exec", "upload"],
    requires=["target"],
    description="Provides mock SSH endpoint and exec/upload capabilities",
)
class MockSshPlugin:
    """Mock SSH capability provider.

    Declares SSH endpoint and derives exec/upload capabilities from it.
    Provides a mock executor that doesn't require actual SSH connectivity.
    """

    @itf_hookimpl
    def session_start_target_capabilities_declare(self, context):
        """Declare SSH endpoint as a target capability."""
        logger.info("MockSshPlugin: declaring SSH endpoint")

        if context.target is None:
            logger.warning("No target available; skipping SSH endpoint")
            return

        # Initialize typed state for SSH endpoint
        endpoint = context.use_state(
            MockSshEndpointState,
            owner="mock_ssh",
            factory=lambda: MockSshEndpointState(
                host="127.0.0.1",
                port=22,
                username="root",
            ),
        )

        # Store in context as a capability spec
        context.target_capability_specs["ssh_endpoint"] = {
            "name": "ssh_endpoint",
            "transport": "ssh.endpoint",
            "host": endpoint.host,
            "port": endpoint.port,
            "username": endpoint.username,
        }

        # Mark as available
        context.target.add_capability("ssh")
        context.capabilities.add("ssh")

        logger.info(f"SSH endpoint declared: {endpoint.username}@{endpoint.host}:{endpoint.port}")

    @itf_hookimpl
    def session_start_capabilities_augment(self, context):
        """Augment with derived capabilities (exec, upload)."""
        logger.info("MockSshPlugin: augmenting with exec/upload capabilities")

        # Check if SSH endpoint exists
        if "ssh_endpoint" not in context.target_capability_specs:
            logger.debug("SSH endpoint not available")
            return

        # Get SSH endpoint configuration
        endpoint_spec = context.target_capability_specs["ssh_endpoint"]
        endpoint = context.get_state(MockSshEndpointState)

        if endpoint is None:
            logger.warning("MockSshEndpointState not initialized")
            return

        # Create executor
        executor = SimpleMockSshExecutor(
            host=endpoint.host,
            port=endpoint.port,
            username=endpoint.username,
        )

        # Store executor in shared resources for use by tests
        context.shared_resources["ssh_executor"] = executor

        # Declare exec capability
        context.shared_resources["exec_capability"] = {
            "transport": "ssh.exec",
            "executor": executor,
        }
        context.capabilities.add("exec")

        # Declare upload capability
        context.shared_resources["upload_capability"] = {
            "transport": "ssh.upload",
            "executor": executor,
        }
        context.capabilities.add("upload")

        logger.info("SSH-based exec and upload capabilities available")

    @itf_hookimpl
    def session_start_readiness_check(self, context):
        """Check SSH readiness."""
        logger.debug("MockSshPlugin: readiness check")

        if "ssh_endpoint" not in context.target_capability_specs:
            return OracleResult.fail_check(
                name="mock_ssh_ready",
                details="SSH endpoint not declared",
                blocking=False,
            )

        if "exec" not in context.capabilities:
            return OracleResult.fail_check(
                name="mock_ssh_ready",
                details="exec capability not available",
                blocking=False,
            )

        if "upload" not in context.capabilities:
            return OracleResult.fail_check(
                name="mock_ssh_ready",
                details="upload capability not available",
                blocking=False,
            )

        endpoint = context.get_state(MockSshEndpointState)
        return OracleResult.pass_check(
            name="mock_ssh_ready",
            details=f"SSH ready: {endpoint.username}@{endpoint.host}:{endpoint.port}",
        )
