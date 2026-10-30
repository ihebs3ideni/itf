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
"""Packs sharing the `score.itf.packs` namespace are still separate contributors (D-28)."""

from __future__ import annotations

import inspect
import types

import pytest

from score.itf.core.engine.registry import (
    CrossContributorImport,
    _check_import_statements,
    contributor_of,
)


@pytest.mark.parametrize(
    "module, contributor",
    [
        ("score.itf.packs.alpha.real.providers", "score.itf.packs.alpha"),
        ("score.itf.packs.alpha", "score.itf.packs.alpha"),
        ("score.itf.packs.beta.plugin", "score.itf.packs.beta"),
        ("my_pack.providers", "my_pack"),
    ],
)
def test_contributor_is_the_pack_under_a_namespace_else_the_top_level_package(module, contributor):
    assert contributor_of(module) == contributor


def _check(source: str, own: str = "score.itf.packs.alpha.steps"):
    """Run the import-statement check on `source` as if it were module `own`."""
    tops = {"score.itf.packs.alpha", "score.itf.packs.beta"}
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(inspect, "getsource", lambda _module: source)
        _check_import_statements(own, types.ModuleType(own), tops)


def test_a_pack_importing_another_pack_is_refused():
    with pytest.raises(CrossContributorImport, match="score.itf.packs.beta"):
        _check("from score.itf.packs.beta.providers import Thing\n")


def test_a_pack_may_import_its_own_modules():
    _check("from score.itf.packs.alpha.providers import Thing\n")


def test_core_public_modules_are_open_and_internals_are_not():
    _check("from score.itf.core import provides, delivers\nfrom score.itf.core.process import AsyncProcess\n")
    _check("import score.itf as itf\n")
    with pytest.raises(CrossContributorImport, match="internals"):
        _check("from score.itf.core.engine.publish import provides\n")
    with pytest.raises(CrossContributorImport, match="public API"):
        _check("from score.itf.core import Realization\n")
