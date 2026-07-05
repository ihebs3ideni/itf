"""``ctf/cap/network`` -- inspect the target's network identity.

Not every target has a network identity (a local subprocess or an in-process
mock may not), which makes this a good demonstration of a capability that some
targets publish and others do not: tests requiring it skip where it is absent.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

#: The reserved framework contract for this capability.
CONTRACT = "ctf/cap/network"


@runtime_checkable
class Network(Protocol):
    """Report the target's network addressing."""

    def ip(self) -> str:
        """The target's IP address."""
        ...

    def gateway(self) -> str:
        """The target's default gateway."""
        ...
