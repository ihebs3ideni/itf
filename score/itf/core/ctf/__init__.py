"""Composable Target Framework (CTF).

A reusable, pytest-free composition engine for building Devices Under Test (DUT).
The core knows nothing about domains (CAN, SSH, DoIP, ...) or test runners.
Plugins contribute opaque *descriptors* and *providers* keyed by string
*contracts*; the engine resolves a deterministic dependency graph and composes
a runtime :class:`~ctf.dut.DUT`.

CTF is designed to be embedded by test frameworks (e.g. ITF integrates it with
pytest). The kernel never imports pytest — all test-runner knowledge lives in
the integration layer.
"""

from __future__ import annotations

from score.itf.core.ctf.contracts import Provider, provides, requires
from score.itf.core.ctf.descriptor import Descriptor
from score.itf.core.ctf.dut import (
    DUT,
    ContractInfo,
    DeviceProxy,
    MethodInfo,
    build_device_assemblies,
    build_manager,
    compose,
)
from score.itf.core.ctf.errors import (
    CapabilityDisabledError,
    CapabilityUnavailableError,
    CompositionError,
    CyclicDependencyError,
    DuplicateProviderError,
    KeyCollisionError,
    UnresolvedContractError,
)
from score.itf.core.ctf.lifecycle import LifecycleScope
from score.itf.core.ctf.registry import Registry, DeviceRegistryContext
from score.itf.core.ctf.resolver import GraphResolver
from score.itf.core.ctf.assembly import (
    Assembly,
    CompositionPlan,
    RunMode,
    TierReport,
    analyze,
)
from score.itf.core.ctf.target import TARGET_ANCHOR, DescriptorTarget, Target

__all__ = [
    "Descriptor",
    "Provider",
    "provides",
    "requires",
    "Registry",
    "GraphResolver",
    "LifecycleScope",
    "Assembly",
    "CompositionPlan",
    "TierReport",
    "RunMode",
    "analyze",
    "build_manager",
    "DUT",
    "compose",
    "Target",
    "DescriptorTarget",
    "TARGET_ANCHOR",
    "CompositionError",
    "CapabilityDisabledError",
    "CapabilityUnavailableError",
    "UnresolvedContractError",
    "DuplicateProviderError",
    "KeyCollisionError",
    "CyclicDependencyError",
]
