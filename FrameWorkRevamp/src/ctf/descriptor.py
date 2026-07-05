"""The opaque unit of contribution.

A :class:`Descriptor` is a *fact* published by a target. The engine never
interprets ``value``; it only routes it to providers that ``require`` the
descriptor's ``key`` (its contract).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class Descriptor:
    """An opaque, engine-uninterpreted fact.

    Attributes:
        key: The contract this descriptor satisfies (e.g. ``"transport/can"``).
        value: Arbitrary, plugin-owned payload. Opaque to the engine.
        metadata: Optional hints for resolution or debugging.
    """

    key: str
    value: Any = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.key, str) or not self.key:
            raise ValueError("Descriptor.key must be a non-empty string")
