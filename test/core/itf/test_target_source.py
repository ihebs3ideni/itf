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
"""Which composition and which override files a run uses: one resolution, runner-agnostic."""

import pytest

from score.itf.core import TargetSourceError, resolve_overrides, resolve_target


def write(path, text="capabilities: {}\n"):
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_the_explicit_value_wins_over_the_environment_and_pyproject(tmp_path):
    explicit, from_env = write(tmp_path / "a.yaml"), write(tmp_path / "b.yaml")
    (tmp_path / "pyproject.toml").write_text('[tool.itf]\ntarget = "c.yaml"\n', encoding="utf-8")
    write(tmp_path / "c.yaml")
    source = resolve_target(explicit, environ={"ITF_TARGET": from_env}, root=tmp_path, explicit_origin="--itf-target")
    assert (source.value, source.origin) == (explicit, "--itf-target")
    source = resolve_target(None, environ={"ITF_TARGET": from_env}, root=tmp_path)
    assert (source.value, source.origin) == (from_env, "ITF_TARGET")
    source = resolve_target(None, environ={}, root=tmp_path)
    assert source.value == str(tmp_path / "c.yaml") and "[tool.itf] target" in source.origin


def test_nothing_configured_is_none(tmp_path):
    assert resolve_target(None, environ={}, root=tmp_path) is None
    assert resolve_overrides((), environ={}, root=tmp_path) == ()


def test_a_value_may_be_inline_text(tmp_path):
    source = resolve_target("capabilities:\n  a: b.c\n", environ={}, root=tmp_path)
    assert source.is_inline and "inline" in source.describe() or "<inline>" in source.describe()


def test_a_value_that_is_neither_file_nor_yaml_is_an_error_saying_where_it_looked(tmp_path):
    with pytest.raises(TargetSourceError, match="not an existing file and not inline YAML/JSON text"):
        resolve_target("missing.yaml", environ={}, root=tmp_path, explicit_origin="--itf-target")


def test_a_build_generated_document_is_the_last_resort(tmp_path):
    document = write(tmp_path / "gen.yaml")
    source = resolve_target(None, environ={"ITF_TARGET_DOCUMENT": document}, root=tmp_path)
    assert source.origin == "ITF_TARGET_DOCUMENT"


def test_overrides_come_from_the_runner_then_the_environment_then_pyproject(tmp_path):
    one, two = write(tmp_path / "one.yaml"), write(tmp_path / "two.yaml")
    assert [s.value for s in resolve_overrides([one, two], environ={}, root=tmp_path)] == [one, two]
    env = {"ITF_OVERRIDE": f"{one}:{two}"}
    assert [s.value for s in resolve_overrides((), environ=env, root=tmp_path)] == [one, two]
    (tmp_path / "pyproject.toml").write_text('[tool.itf]\noverride = "one.yaml"\n', encoding="utf-8")
    assert [s.value for s in resolve_overrides((), environ={}, root=tmp_path)] == [one]
