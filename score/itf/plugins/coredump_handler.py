"""Coredump contributor plugin for Oracle criteria."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from score.itf.framework import OracleResult, itf_hookimpl, plugin_contract

logger = logging.getLogger(__name__)


@dataclass
class CoredumpLedgerState:
    """Tracks coredump files observed before/after each test."""

    coredump_dir: Path | None = None
    whitelist: set[str] = field(default_factory=set)
    before_files: dict[str, set[str]] = field(default_factory=dict)
    new_files_by_test: dict[str, list[str]] = field(default_factory=dict)


@plugin_contract(
    name="score.itf.plugins.coredump_handler",
    provides=["coredump_criteria"],
    description="Collects coredumps around test execution and contributes Oracle criteria.",
)
class CoredumpHandlerPlugin:
    """Tracks coredumps and contributes pass/fail criteria to Oracle."""

    def pytest_addoption(self, parser):
        parser.addoption(
            "--itf-coredump-dir",
            action="store",
            default=None,
            help="Optional directory where core dump files are collected.",
        )
        parser.addoption(
            "--itf-coredump-whitelist",
            action="append",
            default=[],
            help="Allowed coredump filename pattern (exact filename match). Repeatable.",
        )

    @itf_hookimpl
    def session_start_shared_resources_configure(self, context):
        state = context.use_state(
            CoredumpLedgerState,
            owner="coredump_handler",
            factory=CoredumpLedgerState,
        )

        if context.pytest_config is None:
            return

        coredump_dir = context.pytest_config.getoption("itf_coredump_dir", default=None)
        if coredump_dir:
            state.coredump_dir = Path(coredump_dir)

        for item in context.pytest_config.getoption("itf_coredump_whitelist", default=[]):
            state.whitelist.add(str(item))

    @itf_hookimpl
    def session_start_readiness_check(self, context):
        state = context.use_state(
            CoredumpLedgerState,
            owner="coredump_handler",
            factory=CoredumpLedgerState,
        )

        if state.coredump_dir is None:
            return OracleResult.skip_check(
                name="coredump_handler_ready",
                details="No coredump directory configured",
            )

        if not state.coredump_dir.exists():
            return OracleResult.fail_check(
                name="coredump_handler_ready",
                details=f"Configured coredump dir does not exist: {state.coredump_dir}",
                blocking=True,
            )

        return OracleResult.pass_check(
            name="coredump_handler_ready",
            details=f"Watching coredumps in {state.coredump_dir}",
        )

    @itf_hookimpl
    def pytest_runtest_logstart(self, nodeid, location):
        _ = location
        context = getattr(self, "_itf_context", None)
        if context is None:
            return

        state = context.use_state(
            CoredumpLedgerState,
            owner="coredump_handler",
            factory=CoredumpLedgerState,
        )
        state.before_files[nodeid] = self._list_core_files(state)

    @itf_hookimpl
    def oracle_test_criteria(self, context, nodeid, reports):
        _ = reports
        state = context.use_state(
            CoredumpLedgerState,
            owner="coredump_handler",
            factory=CoredumpLedgerState,
        )

        before = state.before_files.get(nodeid, set())
        after = self._list_core_files(state)
        new_files = sorted(after.difference(before))
        state.new_files_by_test[nodeid] = new_files

        if not new_files:
            return OracleResult.pass_check(
                name="no_unapproved_coredump",
                details="No new coredumps detected",
            )

        disallowed = [f for f in new_files if f not in state.whitelist]
        if not disallowed:
            return OracleResult.pass_check(
                name="no_unapproved_coredump",
                details="Coredumps detected but all are whitelisted",
                metadata={"new_coredumps": new_files, "whitelisted": True},
            )

        return OracleResult.fail_check(
            name="no_unapproved_coredump",
            details=f"Unapproved coredumps detected: {disallowed}",
            blocking=True,
            metadata={"new_coredumps": new_files, "disallowed": disallowed},
        )

    @itf_hookimpl
    def oracle_run_criteria(self, context):
        state = context.use_state(
            CoredumpLedgerState,
            owner="coredump_handler",
            factory=CoredumpLedgerState,
        )
        disallowed_total = []
        for new_files in state.new_files_by_test.values():
            disallowed_total.extend([f for f in new_files if f not in state.whitelist])

        if disallowed_total:
            return OracleResult.fail_check(
                name="run_no_unapproved_coredump",
                details=f"Run has unapproved coredumps: {sorted(set(disallowed_total))}",
                blocking=True,
            )

        return OracleResult.pass_check(
            name="run_no_unapproved_coredump",
            details="No unapproved coredumps across run",
        )

    def _list_core_files(self, state: CoredumpLedgerState) -> set[str]:
        if state.coredump_dir is None or not state.coredump_dir.exists():
            return set()

        names: set[str] = set()
        for path in state.coredump_dir.iterdir():
            if path.is_file() and path.name.startswith("core"):
                names.add(path.name)
        return names
