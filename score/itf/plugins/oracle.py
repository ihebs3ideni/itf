"""Oracle policy plugin for generic verdict evaluation."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from score.itf.framework import OracleResult, itf_hookimpl, plugin_contract

logger = logging.getLogger(__name__)


@dataclass
class OracleState:
    """Oracle state for test and run-level verdict synthesis."""

    known_teardown_whitelist: set[str] = field(default_factory=set)
    node_reports: dict[str, dict[str, str]] = field(default_factory=dict)


@plugin_contract(
    name="score.itf.plugins.oracle",
    provides=["oracle"],
    description="Generic verdict evaluation engine for startup, test, and run outcomes.",
)
class OraclePlugin:
    """Composes base and contributed criteria into final test/run verdicts."""

    def pytest_addoption(self, parser):
        parser.addoption(
            "--itf-known-issues-file",
            action="store",
            default=None,
            help="Optional JSON file describing known issue whitelists.",
        )

    @itf_hookimpl
    def session_start_shared_resources_configure(self, context):
        state = context.use_state(
            OracleState,
            owner="oracle",
            factory=OracleState,
        )

        known_issues_file = None
        if context.pytest_config is not None:
            known_issues_file = context.pytest_config.getoption(
                "itf_known_issues_file",
                default=None,
            )

        if not known_issues_file:
            return

        path = Path(known_issues_file)
        if not path.exists():
            logger.warning("Known issues file not found: %s", path)
            return

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Failed to load known issues file %s: %s", path, exc)
            return

        for nodeid in payload.get("teardown_fail_whitelist", []):
            state.known_teardown_whitelist.add(str(nodeid))

    @itf_hookimpl
    def session_start_readiness_check(self, context):
        return OracleResult.pass_check(
            name="oracle_ready",
            details="Oracle policy engine initialized",
        )

    @itf_hookimpl
    def pytest_runtest_logreport(self, report):
        context = getattr(self, "_itf_context", None)
        if context is None:
            return

        state = context.use_state(OracleState, owner="oracle", factory=OracleState)

        nodeid = report.nodeid
        node_data = state.node_reports.setdefault(nodeid, {})
        node_data[report.when] = report.outcome

        if report.when == "call":
            context.test_raw_outcomes[nodeid] = report.outcome

        if report.when == "setup" and report.outcome == "skipped":
            context.test_raw_outcomes[nodeid] = "skipped"

        # Evaluate once teardown completes to include call + teardown signals.
        if report.when != "teardown":
            return

        criteria: list[OracleResult] = []

        raw_outcome = context.test_raw_outcomes.get(nodeid, "failed")
        if raw_outcome == "skipped":
            context.test_oracle_checks[nodeid] = [
                OracleResult.skip_check(
                    name="pytest_call_passed",
                    details="Test skipped before call phase",
                )
            ]
            context.test_final_outcomes[nodeid] = "skipped"
            return

        criteria.append(
            OracleResult(
                name="pytest_call_passed",
                passed=(raw_outcome == "passed"),
                blocking=True,
                details=f"Raw call outcome is '{raw_outcome}'",
            )
        )

        teardown_outcome = node_data.get("teardown", "passed")
        if teardown_outcome == "failed":
            whitelisted = nodeid in state.known_teardown_whitelist
            criteria.append(
                OracleResult(
                    name="teardown_passed_or_known",
                    passed=whitelisted,
                    blocking=not whitelisted,
                    details=(
                        "Teardown failed but node is in known-issues whitelist"
                        if whitelisted
                        else "Teardown failed and node is not in known-issues whitelist"
                    ),
                )
            )
        else:
            criteria.append(
                OracleResult.pass_check(
                    name="teardown_passed_or_known",
                    details="Teardown passed",
                )
            )

        pm = context.metadata.get("itf_pm")
        if pm is not None:
            contributed = pm.hook.oracle_test_criteria(
                context=context,
                nodeid=nodeid,
                reports=dict(node_data),
            )
            for item in contributed:
                criteria.extend(self._normalize_oracle_contribution(item))

        context.test_oracle_checks[nodeid] = criteria
        blocking_failures = [c for c in criteria if c.blocking and not c.passed]
        context.test_final_outcomes[nodeid] = "failed" if blocking_failures else "passed"

    @itf_hookimpl
    def pytest_sessionfinish(self, session, exitstatus):
        _ = exitstatus
        context = getattr(self, "_itf_context", None)
        if context is None:
            return

        self.finalize_run(context)

    def finalize_run(self, context):
        """Finalize run-level Oracle checks deterministically."""
        if context.run_final_outcome is not None:
            return

        checks: list[OracleResult] = []

        if context.test_final_outcomes:
            all_passed = all(v in {"passed", "skipped"} for v in context.test_final_outcomes.values())
            checks.append(
                OracleResult(
                    name="all_tests_oracle_passed",
                    passed=all_passed,
                    blocking=True,
                    details=(
                        "All test-level Oracle evaluations passed"
                        if all_passed
                        else "At least one test-level Oracle evaluation failed"
                    ),
                )
            )

        pm = context.metadata.get("itf_pm")
        if pm is not None:
            contributed = pm.hook.oracle_run_criteria(context=context)
            for item in contributed:
                checks.extend(self._normalize_oracle_contribution(item))

        context.run_oracle_checks = checks
        blocking_failures = [c for c in checks if c.blocking and not c.passed]
        context.run_final_outcome = "failed" if blocking_failures else "passed"

    def _normalize_oracle_contribution(self, value: Any) -> list[OracleResult]:
        if value is None:
            return []
        if isinstance(value, OracleResult):
            return [value]
        if isinstance(value, list):
            out: list[OracleResult] = []
            for item in value:
                out.extend(self._normalize_oracle_contribution(item))
            return out
        if isinstance(value, dict):
            return [
                OracleResult(
                    name=str(value.get("name", "oracle_criteria")),
                    passed=bool(value.get("passed", False)),
                    blocking=bool(value.get("blocking", False)),
                    details=str(value.get("details", "")),
                    metadata=dict(value.get("metadata", {})),
                )
            ]
        return []
