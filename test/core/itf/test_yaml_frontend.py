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
"""The YAML frontend's merge/extends algorithm, unit-level (docs/octo-kit/30-decisions.md D-31)."""

from __future__ import annotations

import pytest

from score.itf.core.frontends.yaml_config import resolve_document


def test_simple_document_passes_through_unchanged():
    doc = {"setup": {"contracts": [{"token": "itf.capabilities.exec.shell", "gives": ["run"]}]}}
    assert resolve_document(doc) == doc


def test_extends_merges_a_dict_file_as_a_parent(tmp_path):
    base = tmp_path / "base.yaml"
    base.write_text("init:\n  scopes:\n    main:\n      goals: [itf.states.network.reachable]\n")
    derived = tmp_path / "derived.yaml"
    derived.write_text(f"extends: [{base.name}]\ninit:\n  scopes:\n    main:\n      goals: [itf.states.shell.open]\n")

    result = resolve_document(derived)
    assert "extends" not in result
    assert result["init"]["scopes"]["main"]["goals"] == ["itf.states.network.reachable", "itf.states.shell.open"]


def test_extends_resolves_relative_to_the_child_file(tmp_path):
    (tmp_path / "shared").mkdir()
    base = tmp_path / "shared" / "base.yaml"
    base.write_text("setup:\n  contracts: [{token: world.handle, gives: []}]\n")
    derived = tmp_path / "derived.yaml"
    derived.write_text("extends: [shared/base.yaml]\n")

    result = resolve_document(derived)
    assert result["setup"]["contracts"] == [{"token": "world.handle", "gives": []}]


def test_identity_keyed_lists_merge_by_name_overriding_only_named_fields(tmp_path):
    base = tmp_path / "base.yaml"
    base.write_text(
        "setup:\n"
        "  scopes:\n"
        "    main:\n"
        "      nodes:\n"
        "        - {name: shell, using: fake_shell.session, config: {timeout: 5}}\n"
    )
    derived = tmp_path / "derived.yaml"
    derived.write_text(
        f"extends: [{base.name}]\n"
        "setup:\n"
        "  scopes:\n"
        "    main:\n"
        "      nodes:\n"
        "        - {name: shell, config: {timeout: 30}}\n"
    )

    result = resolve_document(derived)
    [node] = result["setup"]["scopes"]["main"]["nodes"]
    assert node == {"name": "shell", "using": "fake_shell.session", "config": {"timeout": 30}}


def test_identity_keyed_lists_keep_unrelated_entries_from_the_base(tmp_path):
    base = tmp_path / "base.yaml"
    base.write_text(
        "init:\n  assumptions:\n    - {token: itf.states.network.reachable, owner: lab, reason: always on}\n"
    )
    derived = tmp_path / "derived.yaml"
    derived.write_text(
        f"extends: [{base.name}]\n"
        "init:\n"
        "  assumptions:\n"
        "    - {token: itf.states.image.present, owner: ci, reason: pre-flashed}\n"
    )

    result = resolve_document(derived)
    tokens = {a["token"] for a in result["init"]["assumptions"]}
    assert tokens == {"itf.states.network.reachable", "itf.states.image.present"}


def test_multi_parent_extends_merges_in_listed_order(tmp_path):
    a = tmp_path / "a.yaml"
    a.write_text("init:\n  scopes:\n    main:\n      goals: [a_state]\n")
    b = tmp_path / "b.yaml"
    b.write_text("init:\n  scopes:\n    main:\n      goals: [b_state]\n")
    child = tmp_path / "child.yaml"
    child.write_text(f"extends: [{a.name}, {b.name}]\n")

    result = resolve_document(child)
    assert result["init"]["scopes"]["main"]["goals"] == ["a_state", "b_state"]


def test_extends_cycle_raises_a_clear_error(tmp_path):
    a = tmp_path / "a.yaml"
    b = tmp_path / "b.yaml"
    a.write_text(f"extends: [{b.name}]\n")
    b.write_text(f"extends: [{a.name}]\n")

    with pytest.raises(ValueError, match="cycle"):
        resolve_document(a)


def test_source_as_dict_path_or_inline_text_yield_the_same_document(tmp_path):
    as_dict = {"setup": {"contracts": [{"token": "world.handle", "gives": []}]}}
    path = tmp_path / "config.yaml"
    path.write_text("setup:\n  contracts: [{token: world.handle, gives: []}]\n")
    as_text = "setup:\n  contracts: [{token: world.handle, gives: []}]\n"

    assert resolve_document(as_dict) == resolve_document(path) == resolve_document(as_text)


class _RecordingScope:
    def __init__(self):
        self.nodes = {}

    def add(self, name, contract=None, *, using=None, bind=None, config=None):
        self.nodes[name] = config

    def scope(self, name):
        return self


def _configs(doc: str) -> dict:
    from score.itf.core.frontends.yaml_config import load_setup

    scope = _RecordingScope()
    load_setup(scope, doc)
    return scope.nodes


def test_config_values_expand_environment_references(monkeypatch):
    monkeypatch.setenv("ITF_TEST_IMAGE", "/out/image.qcow2")
    monkeypatch.setenv("ITF_TEST_PORT", "2222")
    monkeypatch.delenv("ITF_TEST_UNSET", raising=False)
    nodes = _configs(
        "setup:\n  nodes:\n    - name: vm\n      config:\n"
        "        rootfs: ${ITF_TEST_IMAGE}\n"
        "        port: ${ITF_TEST_PORT}\n"
        "        label: 'img=${ITF_TEST_IMAGE}'\n"
        "        user: ${ITF_TEST_UNSET:-root}\n"
        "        literal: '$${ITF_TEST_IMAGE}'\n"
    )
    assert nodes["vm"] == {
        "rootfs": "/out/image.qcow2",
        "port": 2222,
        "label": "img=/out/image.qcow2",
        "user": "root",
        "literal": "${ITF_TEST_IMAGE}",
    }


def test_an_unset_reference_without_default_names_the_node(monkeypatch):
    monkeypatch.delenv("ITF_TEST_UNSET", raising=False)
    with pytest.raises(ValueError, match=r"node gw\.shell config 'password'.*ITF_TEST_UNSET"):
        _configs(
            "setup:\n  scopes:\n    gw:\n      nodes:\n"
            "        - {name: shell, config: {password: '${ITF_TEST_UNSET}'}}\n"
        )
