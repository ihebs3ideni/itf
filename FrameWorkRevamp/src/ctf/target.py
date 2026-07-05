"""Targets are sources of facts.

A target does not declare capabilities; it publishes :class:`~ctf.descriptor.Descriptor`
objects. Capability providers consume those descriptors by contract key.
"""

from __future__ import annotations

from typing import Iterable

from ctf.descriptor import Descriptor

#: The well-known anchor contract every target exposes. It is the *root* of the
#: mandatory bring-up spine: the ``@requires`` closure reachable from this
#: contract is what MUST resolve for any test environment to exist. Capabilities
#: attach *above* the anchor by requiring it (or a fact it carries), so they sit
#: outside the spine and are treated as additive.
TARGET_ANCHOR = "ctf/target"


class Target:
    """Abstract source of descriptors (facts)."""

    def descriptors(self) -> Iterable[Descriptor]:  # pragma: no cover - interface
        raise NotImplementedError


class DescriptorTarget(Target):
    """A concrete target that publishes a fixed list of descriptors."""

    def __init__(self, descriptors: Iterable[Descriptor]) -> None:
        self._descriptors = tuple(descriptors)

    def descriptors(self) -> Iterable[Descriptor]:
        return self._descriptors
