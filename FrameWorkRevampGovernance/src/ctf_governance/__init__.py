"""CTF ecosystem governance.

An optional layer that governs a CTF ecosystem: contract namespacing,
catalog/discovery, and duplicate/collision detection. Depends on ``ctf``;
``ctf`` never depends on this package.
"""

from __future__ import annotations

from ctf_governance.catalog import (
    Catalog,
    ContractEntry,
    Finding,
    PointEntry,
    audit,
    build_catalog,
)
from ctf_governance.collector import Contribution, ProviderInfo, collect, inspect_plugin
from ctf_governance.naming import (
    DEFAULT_POLICY,
    NamespacePolicy,
    is_valid,
    validate_contract,
)
from ctf_governance.plugin import CtfGovernanceWarning, GovernanceViolation

__all__ = [
    "NamespacePolicy",
    "DEFAULT_POLICY",
    "validate_contract",
    "is_valid",
    "Contribution",
    "ProviderInfo",
    "inspect_plugin",
    "collect",
    "Catalog",
    "ContractEntry",
    "PointEntry",
    "Finding",
    "build_catalog",
    "audit",
    "GovernanceViolation",
    "CtfGovernanceWarning",
]
