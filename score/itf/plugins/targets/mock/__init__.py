"""Mock target package — in-memory fake for unit/integration testing.

Library exports: MockRuntime, MockExecResult.
Plugin wiring lives in ``plugin.py`` (loaded via pytest_plugins).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MockExecResult:
    exit_code: int = 0
    output: bytes = b""


@dataclass
class MockRuntime:
    """In-memory target runtime for testing."""

    commands: list = field(default_factory=list)
    files: dict = field(default_factory=dict)
    _default_exit_code: int = 0

    def execute(self, command: str) -> MockExecResult:
        self.commands.append(command)
        return MockExecResult(exit_code=self._default_exit_code, output=b"")

    def upload(self, local_path: str, remote_path: str) -> None:
        self.files[remote_path] = local_path

    def download(self, remote_path: str, local_path: str) -> None:
        if remote_path not in self.files:
            raise FileNotFoundError(remote_path)

    def restart(self) -> None:
        self.commands.append("__restart__")


__all__ = ["MockRuntime", "MockExecResult"]
