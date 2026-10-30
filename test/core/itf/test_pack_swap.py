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
"""P7-style pack swap, generalized: swapping a pack for another filling the same contract with
the same provider/action names changes only `itf_packs()`, no test or other pack changes
(docs/octo-kit/21-acceptance.md A-7.5, docs/octo-kit/13-spec-authoring.md §5)."""

from __future__ import annotations

import pytest

from score.itf.core.session import Session


@pytest.mark.parametrize("recipe", ["fake_kv_recipe", "fake_kv_recipe_swapped"])
def test_pack_swap_resolves_and_brings_up_unchanged(tmp_path, recipe):
    session = Session([recipe], run_dir=tmp_path / recipe)
    session.resolve()
    session.bring_up()
    store = session.target.main.store
    store.put("k", "v")
    assert store.get("k") == "v"
    session.close()


def test_pack_swap_changes_only_the_implementation_class(tmp_path):
    a = Session(["fake_kv_recipe"], run_dir=tmp_path / "a")
    a.resolve()
    a.bring_up()
    a_type = type(a.target.main.store).__name__
    a.close()

    b = Session(["fake_kv_recipe_swapped"], run_dir=tmp_path / "b")
    b.resolve()
    b.bring_up()
    b_type = type(b.target.main.store).__name__
    b.close()

    assert a_type == "Store"
    assert b_type == "AltStore"
    assert a.target.main.tokens() == b.target.main.tokens()
