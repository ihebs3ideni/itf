"""Composable Test Ecosystem (CTF).

A semantic-agnostic composition engine hosted on pytest. The core knows nothing
about domains (CAN, SSH, DoIP, ...). Plugins contribute opaque *descriptors* and
*providers* keyed by string *contracts*; the engine resolves a deterministic
dependency graph and composes a runtime :class:`~ctf.dut.DUT`.
"""

from __future__ import annotations

from ctf.contracts import Provider, provides, requires
from ctf.descriptor import Descriptor
from ctf.dut import DUT, build_manager, compose
from ctf.errors import (
    CapabilityUnavailableError,
    CompositionError,
    CyclicDependencyError,
    DuplicateProviderError,
    KeyCollisionError,
    StepCollisionError,
    StepExecutionError,
    UnresolvedContractError,
)
from ctf.lifecycle import LifecycleScope
from ctf.pytest_plugin import get_dut
from ctf.registry import Registry
from ctf.resolver import GraphResolver
from ctf.assembly import (
    Assembly,
    CompositionPlan,
    RunMode,
    TierReport,
    analyze,
)
from ctf.steps import (
    BUILTIN_POINTS,
    ArtifactSink,
    Policy,
    Step,
    StepContext,
    StepRegistry,
)
from ctf.target import TARGET_ANCHOR, DescriptorTarget, Target

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
    "get_dut",
    "Target",
    "DescriptorTarget",
    "TARGET_ANCHOR",
    "Policy",
    "Step",
    "StepRegistry",
    "StepContext",
    "ArtifactSink",
    "BUILTIN_POINTS",
    "CompositionError",
    "CapabilityUnavailableError",
    "UnresolvedContractError",
    "DuplicateProviderError",
    "KeyCollisionError",
    "CyclicDependencyError",
    "StepCollisionError",
    "StepExecutionError",
]
