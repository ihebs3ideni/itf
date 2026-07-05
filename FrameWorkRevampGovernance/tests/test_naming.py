from __future__ import annotations

from ctf_governance.naming import (
    DEFAULT_POLICY,
    NamespacePolicy,
    is_valid,
    validate_contract,
)


def test_well_namespaced_contract_passes():
    assert validate_contract("score/transport/doip") == []
    assert is_valid("score/transport/doip")


def test_wrong_segment_count_is_reported():
    issues = validate_contract("doip/client")
    assert issues
    assert any("segments" in i for i in issues)


def test_unprefixed_is_reported():
    assert not is_valid("client")


def test_uppercase_segment_is_reported():
    issues = validate_contract("score/Transport/doip")
    assert any("lower-snake" in i for i in issues)


def test_empty_contract():
    assert validate_contract("") == ["contract name is empty"]


def test_reserved_names_bypass_policy():
    policy = DEFAULT_POLICY.with_reserved("dut")
    assert is_valid("dut", policy)
    assert not is_valid("other", policy)


def test_custom_segment_count():
    policy = NamespacePolicy(segments=2)
    assert is_valid("doip/client", policy)
    assert not is_valid("score/doip/client", policy)
