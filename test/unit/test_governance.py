# *******************************************************************************
# Copyright (c) 2026 Contributors to the Eclipse Foundation
#
# See the NOTICE file(s) distributed with this work for additional
# information regarding copyright ownership.
#
# This program and the accompanying materials are made available under the
# terms of the Apache License Version 2.0 which is available at
# https://www.apache.org/licenses/LICENSE-2.0
#
# SPDX-License-Identifier: Apache-2.0
# *******************************************************************************
"""Unit tests for the governance plugin."""

import pytest

from score.itf.core.ctf.dut import DUT, build_manager
from score.itf.core.ctf.registry import Registry
from score.itf.plugins.targets.mock import plugin as mock_plugin
from score.itf.plugins.utility.governance.plugin import (
    DEFAULT_POLICY,
    Finding,
    GovernanceViolation,
    GovernanceWarning,
    NamespacePolicy,
    _RESERVED_ALIAS_NAMES,
    audit_aliases,
    audit_composition,
    audit_contracts,
    validate_alias,
    validate_contract,
)


# --------------------------------------------------------------------------
# Contract namespace validation
# --------------------------------------------------------------------------


class TestValidateContract:
    def test_valid_two_segment(self):
        assert validate_contract("ctf/target") == []

    def test_valid_three_segment(self):
        assert validate_contract("itf/cap/exec") == []

    def test_valid_four_segment(self):
        assert validate_contract("itf/target/docker/image") == []

    def test_empty_contract(self):
        issues = validate_contract("")
        assert any("empty" in i for i in issues)

    def test_single_segment_fails(self):
        issues = validate_contract("exec")
        assert any("segments" in i for i in issues)

    def test_bad_prefix(self):
        issues = validate_contract("myorg/cap/exec")
        assert any("prefix" in i for i in issues)

    def test_uppercase_segment(self):
        issues = validate_contract("itf/Cap/exec")
        assert any("lower-snake" in i for i in issues)

    def test_empty_segment(self):
        issues = validate_contract("itf//exec")
        assert any("empty segment" in i for i in issues)

    def test_hyphen_segment(self):
        issues = validate_contract("itf/cap/my-thing")
        assert any("lower-snake" in i for i in issues)

    def test_reserved_passes(self):
        policy = NamespacePolicy(reserved=frozenset({"legacy_name"}))
        assert validate_contract("legacy_name", policy) == []

    def test_custom_prefix(self):
        policy = NamespacePolicy(allowed_prefixes=frozenset({"myorg", "itf"}))
        assert validate_contract("myorg/cap/exec", policy) == []

    def test_no_prefix_restriction(self):
        policy = NamespacePolicy(allowed_prefixes=frozenset())
        assert validate_contract("anything/goes/here", policy) == []


# --------------------------------------------------------------------------
# Alias validation
# --------------------------------------------------------------------------


@pytest.fixture
def registry():
    reg = Registry()
    mock_plugin.pytest_itf_declare(reg, config=None)
    return reg


class TestValidateAlias:
    def test_valid_alias(self, registry):
        issues = validate_alias("shell", "itf/cap/exec", registry)
        assert issues == []

    def test_empty_name(self, registry):
        issues = validate_alias("", "itf/cap/exec", registry)
        assert any("empty" in i for i in issues)

    def test_reserved_name(self, registry):
        issues = validate_alias("require", "itf/cap/exec", registry)
        assert any("shadows" in i for i in issues)

    def test_all_reserved_names_blocked(self, registry):
        for name in _RESERVED_ALIAS_NAMES:
            issues = validate_alias(name, "itf/cap/exec", registry)
            assert issues, f"Expected {name!r} to be blocked"

    def test_slash_in_alias(self, registry):
        issues = validate_alias("itf/cap/exec", "itf/cap/exec", registry)
        assert any("contains '/'" in i for i in issues)

    def test_dangling_target(self, registry):
        issues = validate_alias("phantom", "itf/cap/nonexistent", registry)
        assert any("not registered" in i for i in issues)

    def test_empty_contract(self, registry):
        issues = validate_alias("shell", "", registry)
        assert any("empty" in i for i in issues)


# --------------------------------------------------------------------------
# Full audit
# --------------------------------------------------------------------------


@pytest.fixture
def dut(registry):
    assembly = build_manager(registry)
    assembly.enter()
    d = DUT(assembly)
    yield d
    assembly.exit()


class TestAuditContracts:
    def test_mock_contracts_pass(self, registry):
        findings = audit_contracts(registry)
        # The mock target uses itf/* and ctf/* — all valid
        errors = [f for f in findings if f.severity == "error"]
        assert errors == []

    def test_bad_contract_detected(self):
        from score.itf.core.ctf.contracts import provides
        from score.itf.core.ctf.target import TARGET_ANCHOR

        reg = Registry()

        @provides(TARGET_ANCHOR)
        def anchor():
            return "target"

        @provides("BAD_NAME")
        def bad():
            return "bad"

        reg.register(anchor)
        reg.register(bad)

        findings = audit_contracts(reg)
        bad_findings = [f for f in findings if f.subject == "BAD_NAME"]
        assert len(bad_findings) > 0


class TestAuditAliases:
    def test_valid_aliases_pass(self, dut, registry):
        dut.alias("shell", "itf/cap/exec")
        dut.alias("file_transfer", "itf/cap/file_transfer")
        findings = audit_aliases(dut, registry)
        assert findings == []

    def test_dangling_alias_detected(self, dut, registry):
        dut.alias("ghost", "itf/cap/nonexistent")
        findings = audit_aliases(dut, registry)
        assert any(f.code == "alias" and "not registered" in f.message for f in findings)

    def test_reserved_alias_detected(self, dut, registry):
        # Force-add a bad alias by directly manipulating internals
        dut._aliases["require"] = "itf/cap/exec"
        findings = audit_aliases(dut, registry)
        assert any("shadows" in f.message for f in findings)


class TestAuditComposition:
    def test_clean_composition(self, dut, registry):
        dut.alias("shell", "itf/cap/exec")
        findings = audit_composition(dut, registry)
        errors = [f for f in findings if f.severity == "error"]
        assert errors == []

    def test_mixed_findings(self, dut, registry):
        dut.alias("shell", "itf/cap/exec")
        dut._aliases["require"] = "itf/cap/exec"  # reserved name (error)
        findings = audit_composition(dut, registry)
        errors = [f for f in findings if f.severity == "error"]
        assert len(errors) > 0
