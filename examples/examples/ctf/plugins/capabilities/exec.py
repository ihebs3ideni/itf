"""``ctf/cap/exec`` -- run a command on the target and get its result."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

#: The reserved framework contract for this capability.
CONTRACT = "ctf/cap/exec"


@runtime_checkable
class Exec(Protocol):
    """Execute a shell command on the target."""

    def execute(self, command: str) -> tuple[int, bytes]:
        """Run ``command``; return ``(exit_code, combined_output_bytes)``."""
        ...
