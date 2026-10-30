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
"""The YAML frontend end to end, through the real pytest adapter: a root conftest whose
`itf_setup`/`itf_init` are entirely `load_setup`/`load_init` calls, no `ctx.*` calls of its own
(docs/octo-kit/30-decisions.md D-31)."""

from __future__ import annotations

from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _setup(pytester):
    pytester.syspathinsert(str(FIXTURES_DIR))


def _root_conftest_is(pytester, recipe: str) -> None:
    pytester.makeconftest((FIXTURES_DIR / f"{recipe}.py").read_text())


def test_yaml_recipe_drives_full_lifecycle(pytester):
    _setup(pytester)
    pytester.makepyfile("""
        import score.itf.core as itf

        @itf.requires("itf.capabilities.exec.shell")
        def test_uses_shell(target):
            assert target.has("itf.capabilities.exec.shell")
    """)
    _root_conftest_is(pytester, "yaml_shell_recipe")
    result = pytester.runpytest("-v")
    result.assert_outcomes(passed=1)


def test_itf_config_cli_flag_reaches_the_recipe_through_the_same_entry_point(pytester, monkeypatch):
    monkeypatch.setenv("ITF_CONFIG", "placeholder")  # let monkeypatch own cleanup of the real env var
    _setup(pytester)
    pytester.makepyfile("""
        import score.itf.core as itf

        @itf.requires("itf.capabilities.exec.shell")
        def test_uses_shell(target):
            assert target.has("itf.capabilities.exec.shell")
    """)
    _root_conftest_is(pytester, "yaml_shell_recipe")

    override = """
setup:
  scopes:
    main:
      nodes:
        - {name: world, using: fake_shell.world}
        - {name: shell, contract: itf.capabilities.exec.shell, using: fake_shell.session, bind: {world: world}}
init:
  scopes:
    main:
      goals: [itf.states.shell.open]
"""
    result = pytester.runpytest("--itf-config", override, "--itf-plan")
    result.assert_outcomes(passed=0)  # --itf-plan resolves and prints; runs no tests
    result.stdout.fnmatch_lines(["*itf.states.shell.open*"])
