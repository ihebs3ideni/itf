"""ITF v2 test runner with contract-based plugin orchestration.

Example usage:
    python -m score.itf.runner --scenarios all -- -v
    python -m score.itf.runner --scenarios my_scenario -- -v --itf-log-capture-file test.log --itf-json-report report.json
    python -m score.itf.runner --plugins score.itf.plugins.mock_target score.itf.plugins.mock_ssh -- -v

Environment variables:
    ITF_PLUGINS: Colon-separated list of plugin module paths to load
    ITF_PLUGIN_DIR: Directory containing additional plugins to scan
"""

from __future__ import annotations

import os
import sys
import logging
from pathlib import Path

import pytest
import pluggy

from score.itf.framework import (
    ItfContext,
    ItfHooks,
    run_itf_session_start,
    HOOK_NAMESPACE,
)
from score.itf.framework.plugin_loader import PluginLoader, register_plugins

logging.basicConfig(
    level=logging.INFO,
    format="[%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)


def create_plugin_manager(
    plugin_specs: list[str] | None = None,
    plugin_dir: Path | None = None,
    use_entry_points: bool = True,
) -> pluggy.PluginManager:
    """Create and configure pluggy PluginManager with dynamic plugin loading.

    Args:
        plugin_specs: List of plugin module paths (e.g., "score.itf.plugins.mock_target")
                     If None, uses environment variable ITF_PLUGINS or defaults
        plugin_dir: Directory to scan for plugins
                   If None, uses environment variable ITF_PLUGIN_DIR
        use_entry_points: Whether to load plugins from entry points

    Returns:
        Configured PluginManager with loaded plugins
    """
    pm = pluggy.PluginManager(HOOK_NAMESPACE)
    pm.add_hookspecs(ItfHooks)

    plugins = {}

    # 1. Load from entry points (if enabled)
    if use_entry_points:
        entry_point_plugins = PluginLoader.load_plugins_from_entry_points()
        plugins.update(entry_point_plugins)

    # 2. Load from directory (if specified or in env)
    if plugin_dir is None:
        plugin_dir_env = os.getenv("ITF_PLUGIN_DIR")
        if plugin_dir_env:
            plugin_dir = Path(plugin_dir_env)

    if plugin_dir:
        dir_plugins = PluginLoader.load_plugins_from_directory(plugin_dir)
        plugins.update(dir_plugins)

    # 3. Load from explicit plugin specs
    if plugin_specs is None:
        plugins_env = os.getenv("ITF_PLUGINS", "")
        if plugins_env:
            plugin_specs = plugins_env.split(":")
        else:
            # Default plugins if none specified
            plugin_specs = [
                "score.itf.plugins.mock_target",
                "score.itf.plugins.mock_ssh",
                "score.itf.plugins.coredump_handler",
                "score.itf.plugins.oracle",
                "score.itf.plugins.log_capture",
                "score.itf.plugins.json_report",
            ]

    if plugin_specs:
        spec_plugins = PluginLoader.load_plugins_from_list(plugin_specs)
        plugins.update(spec_plugins)

    # Register all plugins
    register_plugins(pm, plugins)

    logger.info(f"Loaded {len(plugins)} plugins: {list(plugins.keys())}")

    return pm


def run_itf_tests(
    scenario_name: str,
    pytest_args: list[str],
    plugin_specs: list[str] | None = None,
    plugin_dir: Path | None = None,
    use_entry_points: bool = True,
    log_file: Path | None = None,
    report_file: Path | None = None,
) -> int:
    """Run ITF tests for a scenario.

    Args:
        scenario_name: Name of scenario to run
        pytest_args: Arguments to pass to pytest
        plugin_specs: List of plugin module paths to load
        plugin_dir: Directory to scan for plugins
        use_entry_points: Whether to load plugins from entry points
        log_file: Optional path to structured log file
        report_file: Optional path to JSON report file

    Returns:
        pytest exit code
    """
    logger.info(f"Starting ITF session for scenario: {scenario_name}")

    # Create plugin manager with dynamic plugin loading
    pm = create_plugin_manager(
        plugin_specs=plugin_specs,
        plugin_dir=plugin_dir,
        use_entry_points=use_entry_points,
    )

    # Create context
    context = ItfContext()
    context.metadata["itf_pm"] = pm

    # Build pytest args
    full_pytest_args = list(pytest_args)

    if log_file:
        full_pytest_args.extend([
            "--itf-log-capture-file", str(log_file),
        ])

    if report_file:
        full_pytest_args.extend([
            "--itf-json-report", str(report_file),
        ])

    # Build the actual pytest args for collection/execution
    test_args = [
        "tests/",  # Default test location; could be scenario-specific
        "-v",
        *full_pytest_args,
    ]

    plugin_instances = [plugin for _, plugin in pm.list_name_plugin()]

    class _ItfPytestBridge:
        def pytest_configure(self, config):
            context.pytest_config = config
            for plugin in plugin_instances:
                setattr(plugin, "_itf_context", context)
            run_itf_session_start(pm, context)

        def pytest_sessionfinish(self, session, exitstatus):
            _ = exitstatus

            # Finalize run-level Oracle verdict before teardown/report serialization.
            for plugin in plugin_instances:
                finalize = getattr(plugin, "finalize_run", None)
                if callable(finalize):
                    finalize(context)

            orchestrator = context.metadata.get("orchestrator")
            if orchestrator is not None:
                orchestrator.execute_teardown()
            # If Oracle says run failed, make pytest exit non-zero.
            if context.run_final_outcome == "failed" and session.exitstatus == 0:
                session.exitstatus = 1

    try:
        # Run pytest with loaded plugins + ITF lifecycle bridge.
        logger.info("Running tests...")
        bridge = _ItfPytestBridge()
        exit_code = pytest.main(test_args, plugins=[*plugin_instances, bridge])

        return exit_code

    except Exception as exc:
        logger.error(f"ITF session failed: {exc}", exc_info=True)
        return 1

    finally:
        # Safety cleanup in case pytest teardown path did not execute.
        logger.info("Running ITF session teardown safety cleanup...")
        context.run_cleanup()


def main(argv: list[str] | None = None) -> int:
    """Main entry point.

    Args:
        argv: Command-line arguments (defaults to sys.argv[1:])

    Returns:
        Exit code

    Example:
        # Use default plugins
        python -m score.itf.runner -- -v

        # Use specific plugins
        python -m score.itf.runner --plugins score.itf.plugins.mock_target -- -v

        # Use directory of plugins
        python -m score.itf.runner --plugin-dir ./my_plugins -- -v

        # Combine multiple sources
        python -m score.itf.runner --plugins score.itf.plugins.mock_target --plugin-dir ./custom -- -v
    """
    if argv is None:
        argv = sys.argv[1:]

    # Parse arguments
    scenario_name = "example"
    pytest_args = []
    log_file = None
    report_file = None
    plugin_specs: list[str] | None = None
    plugin_dir = None
    use_entry_points = True

    i = 0
    while i < len(argv):
        arg = argv[i]

        if arg == "--scenarios":
            i += 1
            if i < len(argv):
                scenario_name = argv[i]

        elif arg == "--plugins":
            # Collect all plugin specs until next flag
            plugin_specs = []
            i += 1
            while i < len(argv) and not argv[i].startswith("--"):
                plugin_specs.append(argv[i])
                i += 1
            i -= 1  # Back up one since loop will increment

        elif arg == "--plugin-dir":
            i += 1
            if i < len(argv):
                plugin_dir = Path(argv[i])

        elif arg == "--no-entry-points":
            use_entry_points = False

        elif arg == "--itf-log-capture-file":
            i += 1
            if i < len(argv):
                log_file = Path(argv[i])

        elif arg == "--itf-json-report":
            i += 1
            if i < len(argv):
                report_file = Path(argv[i])

        elif arg == "--":
            # Rest is pytest args
            pytest_args = argv[i+1:]
            break

        else:
            pytest_args.append(arg)

        i += 1

    logger.info(f"Running scenario: {scenario_name}")
    if plugin_specs:
        logger.info(f"Plugins: {plugin_specs}")
    if plugin_dir:
        logger.info(f"Plugin directory: {plugin_dir}")
    logger.info(f"pytest args: {pytest_args}")

    return run_itf_tests(
        scenario_name,
        pytest_args,
        plugin_specs=plugin_specs,
        plugin_dir=plugin_dir,
        use_entry_points=use_entry_points,
        log_file=log_file,
        report_file=report_file,
    )


if __name__ == "__main__":
    sys.exit(main())
