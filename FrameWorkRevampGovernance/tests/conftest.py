from __future__ import annotations

import pytest

pytest_plugins = ["pytester"]


@pytest.fixture
def plugins():
    """Import the sample plugin modules used across governance tests."""
    from tests.plugins import (
        bad_namespace,
        collide_a,
        collide_b,
        dangling,
        dup_a,
        dup_b,
        good,
    )

    return {
        "good": good,
        "bad_namespace": bad_namespace,
        "dangling": dangling,
        "dup_a": dup_a,
        "dup_b": dup_b,
        "collide_a": collide_a,
        "collide_b": collide_b,
    }
