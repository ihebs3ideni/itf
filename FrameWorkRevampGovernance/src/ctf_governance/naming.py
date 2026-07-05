"""Contract namespacing policy.

CTF contracts are free-form strings. In a large ecosystem that invites clashes
("client", "target", "config" mean different things to different teams). This
module enforces a convention so contracts are self-describing and collision-
resistant:

    <org>/<domain>/<name>          e.g.  score/transport/doip

Each segment is a lower-snake identifier. A small set of *reserved* names may be
left unprefixed (a blessed standard library shared by the whole ecosystem).

The policy only *reports*; enforcement (warn vs. fail) is decided by callers
(the CLI and the pytest plugin).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace


@dataclass(frozen=True)
class NamespacePolicy:
    """Rules a contract name must follow to be well-namespaced."""

    segments: int = 3
    segment_pattern: str = r"[a-z][a-z0-9_]*"
    separator: str = "/"
    #: Unprefixed names that are explicitly blessed (the standard library).
    reserved: frozenset[str] = field(default_factory=frozenset)

    def with_reserved(self, *names: str) -> "NamespacePolicy":
        return replace(self, reserved=frozenset(self.reserved | set(names)))


#: Default: three lower-snake segments, no reserved names.
DEFAULT_POLICY = NamespacePolicy()


def validate_contract(contract: str, policy: NamespacePolicy = DEFAULT_POLICY) -> list[str]:
    """Return a list of human-readable issues for ``contract`` (empty == OK)."""
    if not isinstance(contract, str) or not contract:
        return ["contract name is empty"]
    if contract in policy.reserved:
        return []

    issues: list[str] = []
    parts = contract.split(policy.separator)
    if len(parts) != policy.segments:
        issues.append(
            f"expected {policy.segments} '{policy.separator}'-separated segments "
            f"(<org>{policy.separator}<domain>{policy.separator}<name>), "
            f"found {len(parts)}"
        )

    matcher = re.compile(f"^{policy.segment_pattern}$")
    for part in parts:
        if not part:
            issues.append("contains an empty segment")
        elif not matcher.match(part):
            issues.append(f"segment {part!r} is not a lower-snake identifier")
    return issues


def is_valid(contract: str, policy: NamespacePolicy = DEFAULT_POLICY) -> bool:
    return not validate_contract(contract, policy)


__all__ = ["NamespacePolicy", "DEFAULT_POLICY", "validate_contract", "is_valid"]
