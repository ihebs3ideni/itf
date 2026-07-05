from __future__ import annotations

import pytest

from ctf.contracts import build_provider, provides, requires


def test_provides_and_requires_ordering():
    @provides("out")
    @requires("a")
    @requires("b")
    def factory(a, b):
        return (a, b)

    provider = build_provider(factory)
    assert provider.provides == "out"
    # Top-to-bottom decorator reading order is preserved.
    assert provider.requires == ("a", "b")
    assert provider.is_generator is False
    assert provider.name == "factory"


def test_requires_multiple_in_one_call():
    @provides("out")
    @requires("a", "b", "c")
    def factory(a, b, c):
        return None

    assert build_provider(factory).requires == ("a", "b", "c")


def test_generator_factory_detected():
    @provides("out")
    def factory():
        yield 1

    assert build_provider(factory).is_generator is True


def test_build_provider_requires_decorator():
    def undecorated():
        return None

    with pytest.raises(ValueError):
        build_provider(undecorated)


@pytest.mark.parametrize("bad", ["", 1])
def test_invalid_contracts_rejected(bad):
    with pytest.raises(ValueError):
        provides(bad)
    with pytest.raises(ValueError):
        requires(bad)
