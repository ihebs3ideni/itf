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
"""Tests for DUT.inspect() and DUT.help() introspection."""

import pytest

from score.itf.core.ctf.contracts import provides, requires
from score.itf.core.ctf.descriptor import Descriptor
from score.itf.core.ctf.dut import DUT, ContractInfo, MethodInfo, build_manager
from score.itf.core.ctf.registry import Registry
from score.itf.core.ctf.target import TARGET_ANCHOR


class FakeClient:
    """A sample returned object with public methods."""

    def connect(self, host: str, port: int = 22) -> None:
        """Open a connection to the remote host."""

    def execute(self, command: str, timeout: int = 30) -> tuple:
        """Execute a command and return (exit_code, output)."""

    def close(self) -> None:
        """Close the connection."""


@provides(TARGET_ANCHOR)
def mock_target():
    """A mock target anchor for testing."""
    return {"name": "mock"}


@provides("itf/cap/client")
@requires(TARGET_ANCHOR)
def client_provider(target) -> FakeClient:
    """Build a FakeClient from the target."""
    return FakeClient()


@provides("itf/cap/simple")
@requires(TARGET_ANCHOR)
def simple_provider(target):
    """A simple provider with no return annotation."""
    return "hello"


@pytest.fixture
def registry():
    reg = Registry()
    reg.register(mock_target)
    reg.register(client_provider)
    reg.register(simple_provider)
    reg.add_descriptor(Descriptor("itf/net/ip", "192.168.1.1"))
    return reg


@pytest.fixture
def dut(registry):
    assembly = build_manager(registry)
    assembly.enter()
    yield DUT(assembly)
    assembly.exit()


class TestInspectSingle:
    """dut.inspect(contract) returns ContractInfo for one contract."""

    def test_inspect_provider_before_materialization(self, dut):
        info = dut.inspect("itf/cap/client")
        assert isinstance(info, ContractInfo)
        assert info.contract == "itf/cap/client"
        assert info.kind == "provider"
        assert info.factory_name == "client_provider"
        assert info.return_type == "FakeClient"
        assert info.requires == (TARGET_ANCHOR,)
        assert info.is_materialized is False
        assert "Build a FakeClient" in (info.docstring or "")

    def test_inspect_provider_after_materialization(self, dut):
        dut.require("itf/cap/client")
        info = dut.inspect("itf/cap/client")
        assert info.is_materialized is True
        # Should have extracted methods from the live object
        method_names = [m.name for m in info.public_methods]
        assert "connect" in method_names
        assert "execute" in method_names
        assert "close" in method_names

    def test_inspect_descriptor(self, dut):
        info = dut.inspect("itf/net/ip")
        assert info.kind == "descriptor"
        assert info.return_type == "str"
        assert info.is_materialized is True

    def test_inspect_via_alias(self, dut):
        dut.alias("client", "itf/cap/client")
        info = dut.inspect("client")
        assert info.contract == "itf/cap/client"

    def test_inspect_no_return_annotation(self, dut):
        info = dut.inspect("itf/cap/simple")
        assert info.return_type is None
        assert info.factory_name == "simple_provider"


class TestInspectAll:
    """dut.inspect() (no args) returns all available contracts."""

    def test_inspect_all_returns_list(self, dut):
        result = dut.inspect()
        assert isinstance(result, list)
        contracts = [info.contract for info in result]
        assert "itf/cap/client" in contracts
        assert "itf/net/ip" in contracts
        assert TARGET_ANCHOR in contracts


class TestHelp:
    """dut.help() returns formatted text."""

    def test_help_single_contract(self, dut):
        text = dut.help("itf/cap/client")
        assert "itf/cap/client" in text
        assert "client_provider" in text
        assert "FakeClient" in text

    def test_help_all_contracts(self, dut):
        text = dut.help()
        assert "itf/cap/client" in text
        assert "itf/net/ip" in text

    def test_help_shows_methods_after_resolve(self, dut):
        dut.require("itf/cap/client")
        text = dut.help("itf/cap/client")
        assert ".connect" in text
        assert ".execute" in text


class TestMethodInfo:
    """MethodInfo carries signature and docstring."""

    def test_method_info_from_resolved(self, dut):
        dut.require("itf/cap/client")
        info = dut.inspect("itf/cap/client")
        connect = next(m for m in info.public_methods if m.name == "connect")
        assert "host" in connect.signature
        assert "Open a connection" in (connect.docstring or "")
