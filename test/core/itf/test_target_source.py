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
"""Which target file, override files and project's policy a run uses: one discovery, for every front."""

import os
import sys

import pytest

from score.itf.core.frontends import target_source as source
from score.itf.core.frontends.target_source import TargetSourceError, discover, load_policy, read_document


def write(path, text="capabilities: {}\n"):
    path.write_text(text, encoding="utf-8")
    return str(path)


def found(root, explicit=None, overrides=(), **kw):
    return discover(explicit, overrides, root=root, environ=kw.pop("environ", {}), **kw)


def test_the_order_is_explicit_then_environment_then_ini_then_pyproject(tmp_path):
    explicit, from_env, from_ini, from_toml = (write(tmp_path / f"{n}.yaml") for n in ("a", "b", "c", "d"))
    (tmp_path / "pytest.ini").write_text("[pytest]\nitf_target = c.yaml\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('[tool.itf]\ntarget = "d.yaml"\n', encoding="utf-8")
    env = {"ITF_TARGET": from_env}
    hit = found(tmp_path, explicit, environ=env, target_file_origin="--itf-target").target_file
    assert (hit.value, hit.origin) == (explicit, "--itf-target")
    hit = found(tmp_path, environ=env).target_file
    assert (hit.value, hit.origin) == (from_env, "ITF_TARGET")
    hit = found(tmp_path).target_file
    assert (hit.value, hit.origin) == (from_ini, "pytest.ini itf_target")
    (tmp_path / "pytest.ini").unlink()
    hit = found(tmp_path).target_file
    assert hit.value == from_toml and hit.origin == "pyproject.toml [tool.itf] target"


def test_the_ini_is_pytest_ini_or_pytest_options_in_pyproject(tmp_path):
    target = write(tmp_path / "x.yaml")
    (tmp_path / "pyproject.toml").write_text('[tool.pytest.ini_options]\nitf_target = "x.yaml"\n', encoding="utf-8")
    hit = found(tmp_path).target_file
    assert hit.value == target and "[tool.pytest.ini_options] itf_target" in hit.origin


def test_nothing_configured_is_nothing(tmp_path):
    result = found(tmp_path)
    assert (result.target_file, result.overrides, result.policy) == (None, (), None)


def test_a_relative_path_is_tried_against_the_working_directory_then_the_root(tmp_path, monkeypatch):
    root, elsewhere = tmp_path / "root", tmp_path / "elsewhere"
    root.mkdir()
    elsewhere.mkdir()
    write(root / "c.yaml")
    monkeypatch.chdir(elsewhere)
    assert found(root, "c.yaml").target_file.value == str(root / "c.yaml")
    write(elsewhere / "c.yaml")
    assert found(root, "c.yaml").target_file.value == str(elsewhere / "c.yaml")
    # a value from a configuration file is relative to that file's directory
    (root / "pytest.ini").write_text("[pytest]\nitf_target = c.yaml\n", encoding="utf-8")
    assert found(root).target_file.value == str(root / "c.yaml")


def test_a_value_may_be_inline_text(tmp_path):
    hit = found(tmp_path, "capabilities:\n  a: b.c\n").target_file
    assert hit.is_inline and "<inline>" in hit.describe()


def test_a_value_that_is_neither_file_nor_yaml_is_an_error_saying_where_it_looked(tmp_path):
    with pytest.raises(TargetSourceError, match="not an existing file and not inline YAML/JSON text"):
        found(tmp_path, "missing.yaml", target_file_origin="--itf-target")


def test_overrides_come_from_the_runner_then_the_environment_then_ini_then_pyproject_with_os_pathsep(tmp_path):
    base, one, two = (write(tmp_path / f"{n}.yaml") for n in ("base", "one", "two"))
    assert [s.value for s in found(tmp_path, base, [one, two]).overrides] == [one, two]
    env = {"ITF_OVERRIDE": os.pathsep.join([one, two])}
    assert [s.value for s in found(tmp_path, base, environ=env).overrides] == [one, two]
    (tmp_path / "pytest.ini").write_text(f"[pytest]\nitf_override = one.yaml{os.pathsep}two.yaml\n", encoding="utf-8")
    assert [s.value for s in found(tmp_path, base).overrides] == [one, two]
    (tmp_path / "pytest.ini").unlink()
    (tmp_path / "pyproject.toml").write_text('[tool.itf]\noverride = "one.yaml"\n', encoding="utf-8")
    assert [s.value for s in found(tmp_path, base).overrides] == [one]


def test_override_files_without_a_target_file_are_an_error(tmp_path):
    with pytest.raises(TargetSourceError, match="override files need a target file"):
        found(tmp_path, overrides=[write(tmp_path / "lab.yaml")])


def test_the_policy_is_the_one_beside_the_target_file_else_the_projects(tmp_path, monkeypatch):
    project, lab = tmp_path / "project", tmp_path / "lab"
    project.mkdir()
    lab.mkdir()
    monkeypatch.chdir(tmp_path)
    write(lab / "lab.itf.yaml")
    write(project / "policy.py", "")
    assert found(project, str(lab / "lab.itf.yaml")).policy == project / "policy.py"
    write(lab / "policy.py", "")
    assert found(project, str(lab / "lab.itf.yaml")).policy == lab / "policy.py"
    assert found(project, "capabilities: {}\n").policy == project / "policy.py"  # inline: the project's


def test_target_files_in_subdirectories_share_the_nearest_policy_above_them(tmp_path, monkeypatch):
    project = tmp_path / "project"
    (project / "targets" / "docker").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    write(project / "targets" / "docker" / "docker.itf.yaml")
    write(project / "targets" / "policy.py", "")
    target = str(project / "targets" / "docker" / "docker.itf.yaml")
    assert found(project, target).policy == project / "targets" / "policy.py"
    write(project / "targets" / "docker" / "policy.py", "")
    assert found(project, target).policy == project / "targets" / "docker" / "policy.py"  # beside wins


def test_a_policy_loads_once_under_a_name_of_its_own(tmp_path):
    first, second = tmp_path / "a" / "policy.py", tmp_path / "b" / "policy.py"
    for path, text in ((first, "NAME = 'first'\n"), (second, "NAME = 'second'\n")):
        path.parent.mkdir()
        path.write_text(text, encoding="utf-8")
    a, b = load_policy(first), load_policy(second)
    assert (a.NAME, b.NAME) == ("first", "second")
    assert load_policy(first) is a
    assert sys.modules[a.__name__] is a and sys.modules[b.__name__] is b and a.__name__ != b.__name__
    assert load_policy(tmp_path / "missing" / "policy.py") is None


def test_one_reader_for_a_file_or_inline_text(tmp_path):
    path = tmp_path / "x.yaml"
    path.write_text("a: 1\n", encoding="utf-8")
    assert read_document(str(path)) == ("a: 1\n", path.resolve())
    assert read_document("b: 2\n") == ("b: 2\n", None)
    assert source.read_document(path)[1] == path.resolve()
