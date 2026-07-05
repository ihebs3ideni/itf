"""Shared *scenario* vocabulary for the CTF example ecosystem.

Where a capability is a low-level primitive (exec, file transfer), a **scenario**
is a higher-level behaviour a target can stand up and answer -- e.g. "there is an
echo server; send it bytes and get them back". Different targets satisfy the same
scenario contract differently (docker runs a real server on its network, the mock
answers in-process), and a test asserts the scenario works without knowing which
backend answered.
"""

from __future__ import annotations

from . import echo

__all__ = ["echo"]
