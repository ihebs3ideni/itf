"""``ctf/cap/restart`` -- restart the target."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

#: The reserved framework contract for this capability.
CONTRACT = "ctf/cap/restart"


@runtime_checkable
class Restart(Protocol):
    """Restart the target in place."""

    def restart(self) -> None:
        """Restart the target; it must be usable again afterwards."""
        ...
