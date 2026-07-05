from __future__ import annotations

from ctf_governance.collector import collect, inspect_plugin


def test_inspect_captures_providers_and_descriptors(plugins):
    c = inspect_plugin(plugins["good"])
    assert "score/transport/doip" in c.descriptors
    assert "score/doip/client" in c.providers
    info = c.providers["score/doip/client"]
    assert info.requires == ("score/transport/doip",)
    assert info.phase == "READY"


def test_inspect_captures_steps(plugins):
    c = inspect_plugin(plugins["good"])
    assert c.steps["ctf_provision"] == ["good_provision"]
    assert c.policies["ctf_provision"] == "UNIQUE"


def test_inspect_undecorated_hookfns_are_detected(plugins):
    # The sample plugins omit @pytest.hookimpl; collection must still see them.
    c = inspect_plugin(plugins["bad_namespace"])
    assert "client" in c.providers


def test_collect_multiple_plugins(plugins):
    contributions = collect(plugins["good"], plugins["bad_namespace"])
    names = {c.plugin for c in contributions}
    assert any(n.endswith("good") for n in names)
    assert any(n.endswith("bad_namespace") for n in names)
