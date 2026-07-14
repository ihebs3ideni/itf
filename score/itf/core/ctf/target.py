"""Targets are sources of facts.

A target does not declare capabilities; it publishes :class:`~ctf.descriptor.Descriptor`
objects. Capability providers consume those descriptors by contract key.
"""

from __future__ import annotations

from typing import Iterable

from score.itf.core.ctf.descriptor import Descriptor

#: The well-known anchor contract prefix. Any contract starting with this prefix
#: is treated as a target anchor and forms part of the mandatory bring-up spine.
#: The ``@requires`` closure reachable from anchors is what MUST resolve for any
#: test environment to exist. Capabilities attach *above* anchors by requiring
#: them (or facts they carry), so they sit outside the spine and are treated as
#: additive.
#:
#: Single-target setups use ``"ctf/target"`` directly.
#: Multi-target setups use sub-anchors: ``"ctf/target/gateway"``,
#: ``"ctf/target/body_ctrl"``, etc.
ANCHOR_PREFIX = "ctf/target"

#: Default anchor for single-target setups (backward compatible).
TARGET_ANCHOR = "ctf/target"


def is_anchor(contract: str) -> bool:
    """Return True if ``contract`` is a target anchor.

    An anchor is either the exact string ``"ctf/target"`` or any contract
    that starts with ``"ctf/target/"`` (a named sub-anchor).
    """
    return contract == ANCHOR_PREFIX or contract.startswith(ANCHOR_PREFIX + "/")


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
