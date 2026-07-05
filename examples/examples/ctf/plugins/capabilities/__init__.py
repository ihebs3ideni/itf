"""Shared capability *vocabulary* for the CTF example ecosystem.

A capability is a **contract** (a string name) plus an **interface** (a duck-typed
:class:`typing.Protocol`). Both live here, in one place, so that:

* every *target* plugin publishes the same contract under the same interface, and
* every *test* codes against the interface without knowing the backing target.

These are the framework-reserved ``ctf/cap/*`` contracts. A target satisfies a
capability by providing its ``CONTRACT`` with an object matching its ``Protocol``.
Swap the target and the capability is satisfied differently but identically-shaped;
a target that does not publish a capability makes tests requiring it skip.
"""

from __future__ import annotations

from . import exec, file_transfer, network, ping, restart

__all__ = ["exec", "file_transfer", "network", "ping", "restart"]
