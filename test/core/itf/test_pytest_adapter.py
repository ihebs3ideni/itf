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
"""The pytest adapter: `--itf-target`, overrides, gating, the `target` fixture, errors before any test."""

import kv_parts
import pytest

CONFTEST = 'pytest_plugins = ["kv_parts"]\n'
TARGET = "capabilities:\n  store: project.store\n  view: project.view\ngoals:\n  - state: kv.seeded\n    by: project.seed_a\n"
TEST = """
import score.itf as itf

def test_roles(target):
    assert target.view.read("seeded") == "a"

@itf.requires("command")
def test_needs_a_command(target):
    raise AssertionError("must have been deselected")

@itf.requires("store", contract="kv.store")
def test_needs_the_store(target):
    assert target.store.name
"""


@pytest.fixture(autouse=True)
def reset():
    kv_parts.EVENTS.clear()


def project(pytester, target=TARGET, ini=""):
    pytester.makeconftest(CONFTEST)
    pytester.makepyfile(test_it=TEST)
    pytester.makefile(".yaml", target=target)
    if ini:
        pytester.makeini(ini)


def test_a_composition_given_on_the_command_line_builds_the_target(pytester):
    project(pytester)
    result = pytester.runpytest("--itf-target=target.yaml")
    result.assert_outcomes(passed=2, deselected=1)
    assert kv_parts.EVENTS[-1] == "store closed"


def test_the_ini_option_configures_the_target(pytester):
    project(pytester, ini="[pytest]\nitf_target = target.yaml\n")
    pytester.runpytest().assert_outcomes(passed=2, deselected=1)


def test_the_environment_configures_the_target(pytester, monkeypatch):
    project(pytester)
    monkeypatch.setenv("ITF_TARGET", "target.yaml")
    pytester.runpytest().assert_outcomes(passed=2, deselected=1)


def test_an_override_file_changes_one_role(pytester):
    project(pytester)
    pytester.makefile(".yaml", lab="capabilities:\n  store:\n    with:\n      name: lab\n")
    pytester.makepyfile(test_it="def test_named(target):\n    assert target.store.name == 'lab'\n")
    result = pytester.runpytest("--itf-target=target.yaml", "--itf-override=lab.yaml")
    result.assert_outcomes(passed=1)


def test_overrides_come_from_the_environment_too(pytester, monkeypatch):
    project(pytester)
    pytester.makefile(".yaml", lab="capabilities:\n  store:\n    with:\n      name: lab\n")
    pytester.makepyfile(test_it="def test_named(target):\n    assert target.store.name == 'lab'\n")
    monkeypatch.setenv("ITF_OVERRIDE", "lab.yaml")
    pytester.runpytest("--itf-target=target.yaml").assert_outcomes(passed=1)


def test_plan_prints_the_composition_the_plan_and_the_gating_and_runs_nothing(pytester):
    project(pytester)
    result = pytester.runpytest("--itf-target=target.yaml", "--itf-plan")
    out = result.stdout.str()
    assert "Composition:" in out and "store (project.store)" in out and "kv.seeded" in out
    assert "deselected: target has no role 'command'" in out
    assert kv_parts.EVENTS == []


def test_a_composition_that_does_not_compile_stops_before_any_test(pytester):
    project(pytester, target="capabilities:\n  view: project.view\n")
    result = pytester.runpytest("--itf-target=target.yaml")
    assert result.ret != 0
    out = result.stdout.str() + result.stderr.str()
    assert "plan failed at gate 1" in out and "Candidates: project.store" in out


def test_a_composition_error_is_reported_as_rejected(pytester):
    project(pytester, target="parts:\n  store: project.store\n")
    result = pytester.runpytest("--itf-target=target.yaml")
    assert "composition rejected" in result.stdout.str() + result.stderr.str()


def test_an_unusable_target_value_is_a_usage_error(pytester):
    project(pytester)
    result = pytester.runpytest("--itf-target=missing.yaml")
    assert result.ret == 4
    assert "no usable composition" in result.stdout.str() + result.stderr.str()


def test_overrides_without_a_target_are_a_usage_error(pytester):
    pytester.makefile(".yaml", lab="capabilities: {}\n")
    pytester.makepyfile(test_it="def test_x(): pass\n")
    result = pytester.runpytest("--itf-override=lab.yaml")
    assert result.ret == 4


def test_without_any_composition_the_target_fixture_says_so(pytester):
    pytester.makepyfile(test_it="def test_x(target): pass\n")
    result = pytester.runpytest()
    result.assert_outcomes(errors=1)
    assert "no composition" in result.stdout.str()


def test_strict_gating_turns_a_deselection_into_a_failure(pytester):
    project(pytester)
    result = pytester.runpytest("--itf-target=target.yaml", "--itf-strict-gating")
    result.assert_outcomes(passed=2, errors=1)
    assert "itf gating (strict)" in result.stdout.str()
