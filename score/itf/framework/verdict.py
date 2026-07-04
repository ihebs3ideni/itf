"""Structured readiness and verdict results."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class VerdictType(Enum):
    """Type of verdict."""
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"
    WARN = "warn"


@dataclass
class OracleResult:
    """Structured readiness or verdict check result.

    Attributes:
        name: Check name (e.g., "docker_dependencies", "ssh_connection")
        passed: Whether the check passed
        verdict_type: Type of verdict (pass/fail/skip/warn)
        blocking: Whether failure blocks session startup
        details: Human-readable details or error message
        metadata: Additional structured data
    """

    name: str
    passed: bool = False
    verdict_type: VerdictType = VerdictType.FAIL
    blocking: bool = False
    details: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Synchronize passed/verdict_type."""
        if self.passed and self.verdict_type == VerdictType.FAIL:
            self.verdict_type = VerdictType.PASS
        elif not self.passed and self.verdict_type == VerdictType.PASS:
            self.verdict_type = VerdictType.FAIL

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dict."""
        return {
            "name": self.name,
            "passed": self.passed,
            "verdict_type": self.verdict_type.value,
            "blocking": self.blocking,
            "details": self.details,
            "metadata": self.metadata,
        }

    @staticmethod
    def pass_check(
        name: str,
        details: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> OracleResult:
        """Create a passing result."""
        return OracleResult(
            name=name,
            passed=True,
            verdict_type=VerdictType.PASS,
            details=details,
            metadata=metadata or {},
        )

    @staticmethod
    def fail_check(
        name: str,
        details: str = "",
        blocking: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> OracleResult:
        """Create a failing result."""
        return OracleResult(
            name=name,
            passed=False,
            verdict_type=VerdictType.FAIL,
            blocking=blocking,
            details=details,
            metadata=metadata or {},
        )

    @staticmethod
    def skip_check(
        name: str,
        details: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> OracleResult:
        """Create a skipped result."""
        return OracleResult(
            name=name,
            passed=True,
            verdict_type=VerdictType.SKIP,
            details=details,
            metadata=metadata or {},
        )

    @staticmethod
    def warn_check(
        name: str,
        details: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> OracleResult:
        """Create a warning result."""
        return OracleResult(
            name=name,
            passed=True,
            verdict_type=VerdictType.WARN,
            details=details,
            metadata=metadata or {},
        )
