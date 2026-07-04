"""ITF lifecycle hooks for plugin orchestration."""

from __future__ import annotations

import pluggy

# Hook namespace for all ITF domain hooks
HOOK_NAMESPACE = "itf.hook"
hookspec = pluggy.HookspecMarker(HOOK_NAMESPACE)
itf_hookimpl = pluggy.HookimplMarker(HOOK_NAMESPACE)


class ItfHooks:
    """Specification of ITF lifecycle hooks.

    Hook phases are ordered to ensure proper setup/teardown:
    1. session_start_* phases run in order during session setup
    2. test_* phases run per test
    3. session_finish_* phases run during teardown

    Plugins implement these hooks to participate in the lifecycle.
    """

    # === STARTUP PHASES (ordered) ===

    @hookspec
    def session_start_profile_resolve(context):
        """Phase 1: Resolve execution profile and CLI options.

        Plugins read pytest options and set defaults in context.

        Args:
            context: ItfContext
        """

    @hookspec
    def session_start_target_create(context):
        """Phase 2: Create/initialize the target under test.

        Args:
            context: ItfContext (sets context.target)
        """

    @hookspec
    def session_start_target_prepare(context):
        """Phase 3: Prepare the target (e.g., configure, provision).

        Args:
            context: ItfContext
        """

    @hookspec
    def session_start_target_capabilities_declare(context):
        """Phase 4: Declare capabilities provided by the target.

        Plugins populate context.target_capability_specs and context.capabilities.

        Args:
            context: ItfContext
        """

    @hookspec
    def session_start_capabilities_augment(context):
        """Phase 5: Augment capabilities (compose, wrap, extend).

        E.g., mock SSH adds exec/upload capabilities based on ssh_endpoint.

        Args:
            context: ItfContext
        """

    @hookspec
    def session_start_shared_resources_configure(context):
        """Phase 6: Configure shared resources (services, config, data).

        Args:
            context: ItfContext (populates context.shared_resources)
        """

    @hookspec
    def session_start_services_start(context):
        """Phase 7: Start services (DLT receivers, log aggregators, etc.).

        Args:
            context: ItfContext
        """

    @hookspec
    def session_start_logging_start(context):
        """Phase 8: Start logging and capture.

        Args:
            context: ItfContext
        """

    @hookspec
    def session_start_readiness_check(context):
        """Phase 9: Readiness checks before tests run.

        Plugins validate their assumptions and return OracleResult.

        Args:
            context: ItfContext

        Returns:
            OracleResult or list of OracleResult
        """

    @hookspec
    def session_start_environment_freeze(context):
        """Phase 10: Final setup; test environment is now frozen.

        Args:
            context: ItfContext
        """

    # === TEARDOWN PHASES (reversed) ===

    @hookspec
    def session_finish_logging_stop(context):
        """Tear down logging and capture.

        Args:
            context: ItfContext
        """

    @hookspec
    def session_finish_services_stop(context):
        """Stop services.

        Args:
            context: ItfContext
        """

    @hookspec
    def session_finish_shared_resources_cleanup(context):
        """Clean up shared resources.

        Args:
            context: ItfContext
        """

    @hookspec
    def session_finish_target_cleanup(context):
        """Clean up the target.

        Args:
            context: ItfContext
        """

    # === TEST LIFECYCLE ===

    @hookspec
    def pytest_configure(config):
        """pytest configuration hook (passed through).

        Args:
            config: pytest Config
        """

    @hookspec
    def pytest_runtest_logstart(nodeid, location):
        """pytest test start (passed through).

        Args:
            nodeid: pytest node id
            location: Test location
        """

    @hookspec
    def pytest_runtest_logreport(report):
        """pytest test report (passed through).

        Args:
            report: pytest TestReport
        """

    @hookspec
    def pytest_sessionfinish(session, exitstatus):
        """pytest session finish (passed through).

        Args:
            session: pytest Session
            exitstatus: Exit status code
        """

    # === ORACLE CONTRIBUTIONS ===

    @hookspec
    def oracle_test_criteria(context, nodeid, reports):
        """Contribute additional per-test Oracle criteria.

        Args:
            context: ItfContext
            nodeid: pytest node id for the test case
            reports: Mapping of phase -> outcome/details for setup/call/teardown

        Returns:
            OracleResult or list[OracleResult]
        """

    @hookspec
    def oracle_run_criteria(context):
        """Contribute additional final run Oracle criteria.

        Args:
            context: ItfContext

        Returns:
            OracleResult or list[OracleResult]
        """


# Ordered list of startup phases for orchestration
STARTUP_PHASES = (
    "session_start_profile_resolve",
    "session_start_target_create",
    "session_start_target_prepare",
    "session_start_target_capabilities_declare",
    "session_start_capabilities_augment",
    "session_start_shared_resources_configure",
    "session_start_services_start",
    "session_start_logging_start",
    "session_start_readiness_check",
    "session_start_environment_freeze",
)

TEARDOWN_PHASES = (
    "session_finish_logging_stop",
    "session_finish_services_stop",
    "session_finish_shared_resources_cleanup",
    "session_finish_target_cleanup",
)
