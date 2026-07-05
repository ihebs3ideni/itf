"""Run-mode semantics: mandatory spine vs additive capabilities.

The asymmetry under test: a missing dependency *inside the target spine* fails
the run in both modes, while a missing dependency of an *additive* capability
only fails in STRICT -- in LOOSE it is recorded and its dependents skip.
"""

from __future__ import annotations

import pytest

from ctf.assembly import RunMode
from ctf.contracts import provides, requires
from ctf.descriptor import Descriptor
from ctf.dut import build_manager
from ctf.errors import UnresolvedContractError
from ctf.target import TARGET_ANCHOR


def _registry_with_missing_additive() -> Registry:
    from ctf.registry import Registry

    registry = Registry()
    registry.add_descriptor(Descriptor("ctf/env/testbench", value="bench"))

    @registry.register
    @provides(TARGET_ANCHOR)
    @requires("ctf/env/testbench")
    def target(bench):
        return "target"

    # Additive capability requiring something nobody provides.
    @registry.register
    @provides("ctf/cap/ssh")
    @requires(TARGET_ANCHOR, "ctf/net/endpoint")
    def ssh(target, endpoint):  # pragma: no cover - never built
        return "ssh"

    return registry


def _registry_with_broken_spine() -> Registry:
    from ctf.registry import Registry

    registry = Registry()

    # The anchor's own substrate is missing -> spine cannot resolve.
    @registry.register
    @provides(TARGET_ANCHOR)
    @requires("ctf/env/testbench")
    def target(bench):  # pragma: no cover - never built
        return "target"

    return registry


def test_loose_tolerates_missing_additive():
    manager = build_manager(_registry_with_missing_additive(), RunMode.LOOSE)
    assert not manager.available("ctf/cap/ssh")
    assert manager.available(TARGET_ANCHOR)


def test_strict_fails_on_missing_additive():
    with pytest.raises(UnresolvedContractError):
        build_manager(_registry_with_missing_additive(), RunMode.STRICT)


def test_broken_spine_fails_in_loose():
    # A missing spine dependency is fatal even in LOOSE.
    with pytest.raises(UnresolvedContractError):
        build_manager(_registry_with_broken_spine(), RunMode.LOOSE)


def test_broken_spine_fails_in_strict():
    with pytest.raises(UnresolvedContractError):
        build_manager(_registry_with_broken_spine(), RunMode.STRICT)


def test_loose_without_anchor_behaves_strict():
    from ctf.registry import Registry

    registry = Registry()

    @registry.register
    @provides("cap")
    @requires("missing")
    def cap(missing):  # pragma: no cover - never built
        return "cap"

    # No anchor => no declared spine => everything is mandatory even in LOOSE.
    with pytest.raises(UnresolvedContractError):
        build_manager(registry, RunMode.LOOSE)
