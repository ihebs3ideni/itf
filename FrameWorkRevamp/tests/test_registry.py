from __future__ import annotations

import pytest

from ctf.contracts import provides, requires
from ctf.descriptor import Descriptor
from ctf.errors import DuplicateProviderError, KeyCollisionError
from ctf.registry import Registry
from ctf.target import DescriptorTarget


def _provider(registry, contract, deps=()):
    def factory(*args):
        return contract

    factory = provides(contract)(factory)
    if deps:
        factory = requires(*deps)(factory)
    registry.register(factory)


def test_add_descriptor_and_query():
    registry = Registry()
    registry.add_descriptor(Descriptor("transport/can", value=42))
    assert registry.has("transport/can")
    assert registry.descriptor("transport/can").value == 42
    assert registry.provider("transport/can") is None


def test_add_target_expands_descriptors():
    registry = Registry()
    registry.add_target(
        DescriptorTarget([Descriptor("a"), Descriptor("b")])
    )
    assert registry.contracts() == frozenset({"a", "b"})


def test_duplicate_descriptor_rejected():
    registry = Registry()
    registry.add_descriptor(Descriptor("a"))
    with pytest.raises(DuplicateProviderError):
        registry.add_descriptor(Descriptor("a"))


def test_duplicate_provider_rejected():
    registry = Registry()
    _provider(registry, "a")
    with pytest.raises(DuplicateProviderError):
        _provider(registry, "a")


def test_descriptor_provider_collision_both_directions():
    registry = Registry()
    registry.add_descriptor(Descriptor("a"))
    with pytest.raises(KeyCollisionError):
        _provider(registry, "a")

    registry2 = Registry()
    _provider(registry2, "b")
    with pytest.raises(KeyCollisionError):
        registry2.add_descriptor(Descriptor("b"))
