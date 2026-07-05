from __future__ import annotations

import pytest

from ctf.descriptor import Descriptor


def test_descriptor_defaults():
    d = Descriptor("transport/can")
    assert d.key == "transport/can"
    assert d.value is None
    assert d.metadata == {}


def test_descriptor_is_frozen():
    d = Descriptor("x", value=1)
    with pytest.raises(Exception):
        d.value = 2  # type: ignore[misc]


@pytest.mark.parametrize("bad", ["", None, 123])
def test_descriptor_rejects_bad_key(bad):
    with pytest.raises(ValueError):
        Descriptor(bad)  # type: ignore[arg-type]
