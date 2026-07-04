"""JSON report exporter plugin for test results."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from score.itf.framework import (
    plugin_contract,
    itf_hookimpl,
    OracleResult,
)

logger = logging.getLogger(__name__)


@dataclass
class TestResultEntry:
    """A single test result entry."""
    test_name: str
    test_path: str
    raw_outcome: str  # "passed", "failed", "skipped"
    final_outcome: str = "unknown"
    duration: float = 0.0
    error_message: str = ""
    error_details: str = ""
    oracle_checks: list[dict[str, Any]] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class TestReportState:
    """JSON report state.

    Owned by: json_report plugin
    Stored in: context.use_state(TestReportState)
    """
    file_path: Path | None = None
    test_results: list[TestResultEntry] = field(default_factory=list)
    test_results_by_nodeid: dict[str, TestResultEntry] = field(default_factory=dict)
    session_start_time: datetime = field(default_factory=datetime.now)
    session_end_time: datetime | None = None


@plugin_contract(
    name="score.itf.plugins.json_report",
    provides=["json_report"],
    description="Exports test results to JSON format",
)
class JsonReportPlugin:
    """JSON report exporter.

    Collects test results and exports to JSON with:
    - Global session info (start time, duration, target, capabilities)
    - Per-test info (name, path, outcome, duration, errors)

    Lifecycle:
    1. Configure: determine report file path
    2. Freeze: validate report path is writable
    3. Cleanup: write final report (after tests complete)
    """

    def pytest_addoption(self, parser):
        """Register pytest options."""
        parser.addoption(
            "--itf-json-report",
            action="store",
            default=None,
            help="Path to JSON report file",
        )

    @itf_hookimpl
    def session_start_shared_resources_configure(self, context):
        """Configure JSON report from pytest options."""
        logger.debug("JsonReportPlugin: configuring")

        if context.pytest_config is None:
            logger.debug("No pytest config available; skipping JSON report config")
            return

        report_file = context.pytest_config.getoption(
            "itf_json_report",
            default=None,
        )

        if report_file:
            path = Path(report_file)
            path.parent.mkdir(parents=True, exist_ok=True)

            state = context.use_state(
                TestReportState,
                owner="json_report",
                factory=lambda: TestReportState(
                    file_path=path,
                    session_start_time=datetime.now(),
                ),
            )
            state.file_path = path

            context.shared_resources["json_report_file"] = str(path)
            logger.info(f"JSON report configured: {path}")

    @itf_hookimpl
    def session_start_environment_freeze(self, context):
        """Validate report path is writable."""
        logger.debug("JsonReportPlugin: environment frozen")

        state = context.get_state(TestReportState)
        if state and state.file_path:
            # Test that we can write
            try:
                state.file_path.touch()
                logger.debug(f"Report path writable: {state.file_path}")
            except Exception as exc:
                logger.warning(f"Report path not writable: {exc}")

    @itf_hookimpl
    def session_finish_shared_resources_cleanup(self, context):
        """Write final JSON report."""
        logger.info("JsonReportPlugin: writing report")

        state = context.get_state(TestReportState)
        if state is None or state.file_path is None:
            logger.debug("JSON report not configured")
            return

        # Finalize collected test results regardless of pytest hook ordering.
        state.test_results = list(state.test_results_by_nodeid.values())

        state.session_end_time = datetime.now()

        # Build report structure
        report = self._build_report(context, state)

        # Write JSON
        try:
            with open(state.file_path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2)
            logger.info(f"Report written: {state.file_path}")
        except Exception as exc:
            logger.error(f"Failed to write report: {exc}", exc_info=True)

    def _build_report(self, context: Any, state: TestReportState) -> dict:
        """Build the complete report structure."""
        session_duration = (
            (state.session_end_time - state.session_start_time).total_seconds()
            if state.session_end_time
            else 0.0
        )

        # Collect capabilities
        capabilities = list(context.capabilities) if hasattr(context, "capabilities") else []

        # Collect readiness checks
        readiness = []
        for check in context.startup_checks:
            if hasattr(check, "to_dict"):
                readiness.append(check.to_dict())
            elif isinstance(check, dict):
                readiness.append(check)

        # Global section
        tests_payload = []
        for result in state.test_results:
            final_outcome = context.test_final_outcomes.get(result.test_name, result.final_outcome)
            checks = [
                c.to_dict() if hasattr(c, "to_dict") else c
                for c in context.test_oracle_checks.get(result.test_name, result.oracle_checks)
            ]
            payload = asdict(result)
            payload["final_outcome"] = final_outcome
            payload["oracle_checks"] = checks
            tests_payload.append(payload)

        report = {
            "global": {
                "session_start": state.session_start_time.isoformat(),
                "session_end": state.session_end_time.isoformat() if state.session_end_time else None,
                "session_duration_seconds": session_duration,
                "target_info": {
                    "type": "mock" if hasattr(context.target, "__class__") and "Mock" in context.target.__class__.__name__ else "unknown",
                    "hostname": getattr(context.target, "hostname", "unknown") if context.target else None,
                },
                "capabilities": capabilities,
                "readiness_checks": readiness,
                "log_file": context.shared_resources.get("log_capture_file"),
            },
            "tests": tests_payload,
        }

        # Summary
        total_tests = len(state.test_results)
        passed = sum(1 for r in state.test_results if r.final_outcome == "passed")
        failed = sum(1 for r in state.test_results if r.final_outcome == "failed")
        skipped = sum(1 for r in state.test_results if r.final_outcome == "skipped")

        report["summary"] = {
            "total_tests": total_tests,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
        }

        report["oracle"] = {
            "run_final_outcome": context.run_final_outcome,
            "run_checks": [
                c.to_dict() if hasattr(c, "to_dict") else c
                for c in context.run_oracle_checks
            ],
        }

        return report

    @itf_hookimpl
    def session_start_readiness_check(self, context):
        """Check report configuration."""
        logger.debug("JsonReportPlugin: readiness check")

        state = context.get_state(TestReportState)
        if state is None or state.file_path is None:
            return OracleResult.skip_check(
                name="json_report_ready",
                details="JSON report not configured",
            )

        return OracleResult.pass_check(
            name="json_report_ready",
            details=f"Report will be written to {state.file_path}",
        )

    @itf_hookimpl
    def pytest_runtest_logreport(self, report):
        """Collect test results for the report."""
        context = getattr(self, "_itf_context", None)
        if context is None:
            return

        state = context.get_state(TestReportState)
        if state is None:
            return

        # This hook is called after each test
        # We'll collect results that are later written to JSON
        if report.when == "setup" and report.skipped:
            result = TestResultEntry(
                test_name=report.nodeid,
                test_path=report.fspath or "",
                raw_outcome="skipped",
                final_outcome=context.test_final_outcomes.get(report.nodeid, "skipped"),
                duration=report.duration or 0.0,
                error_message="",
                error_details="",
            )
            state.test_results_by_nodeid[report.nodeid] = result

        if report.when == "call":
            # Map outcome
            outcome = report.outcome
            if outcome == "passed":
                outcome = "passed"
            elif outcome == "failed":
                outcome = "failed"
            else:
                outcome = "skipped"

            error_msg = ""
            error_details = ""

            if report.failed:
                if hasattr(report, "longreprtext"):
                    error_details = report.longreprtext
                if hasattr(report, "wasxfail"):
                    error_msg = str(report.wasxfail)

            result = TestResultEntry(
                test_name=report.nodeid,
                test_path=report.fspath or "",
                raw_outcome=outcome,
                final_outcome=context.test_final_outcomes.get(report.nodeid, "unknown"),
                duration=report.duration or 0.0,
                error_message=error_msg,
                error_details=error_details,
            )
            state.test_results_by_nodeid[report.nodeid] = result

        if report.when == "teardown":
            entry = state.test_results_by_nodeid.get(report.nodeid)
            if entry is None:
                return

            entry.final_outcome = context.test_final_outcomes.get(
                report.nodeid,
                entry.raw_outcome,
            )
            entry.oracle_checks = [
                c.to_dict() if hasattr(c, "to_dict") else c
                for c in context.test_oracle_checks.get(report.nodeid, [])
            ]

