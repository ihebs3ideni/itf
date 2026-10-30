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
"""P3: registration, publication, D-28 (docs/octo-kit/21-acceptance.md A-3.*)."""

from __future__ import annotations

import random

import pytest

from score.itf.core.engine.collect import collect_init, collect_setup
from score.itf.core.engine.publish import publish
from score.itf.core.engine.registry import CrossContributorImport, register
from score.itf.core import octo
from score.itf.core.session import PRECEDENCE, ResolutionFailed, Session


def test_a_3_1_provides_and_delivers_record_without_running(tmp_path):
    """Importing a pack whose factory would raise on call still yields a descriptor."""
    import fake_kv.providers as providers

    assert any(d.name == "fake_kv.memory_store" for d in _staged(providers))


def _staged(module):
    from score.itf.core.engine.publish import _STAGING

    return _STAGING.get(module.__name__, [])


def test_a_3_2_publication_is_module_keyed(tmp_path):
    """A module's descriptors are the same whatever else happens to be imported."""
    import fake_kv.providers as providers

    before = list(_staged(providers))
    import fake_shell.providers  # unrelated import

    after = list(_staged(providers))
    assert before == after


def test_a_3_4_claim_sets_are_order_independent(tmp_path):
    orders = [
        ["fake_shell.plugin", "shell_recipe"],
        ["shell_recipe", "fake_shell.plugin"],
    ]
    setup_sets = []
    init_sets = []
    for policies in orders:
        registry = register(list(policies))
        catalog = publish(registry)
        setup_claims = collect_setup(registry, catalog) | frozenset(catalog.providers)
        target_res = octo.resolve_target(setup_claims, precedence=PRECEDENCE)
        assert target_res.ok()
        init_claims = collect_init(registry, catalog, target_res.plan) | frozenset(catalog.actions)
        setup_sets.append(setup_claims)
        init_sets.append(init_claims)
    assert setup_sets[0] == setup_sets[1]
    assert init_sets[0] == init_sets[1]


def test_a_3_4_shuffled_registration_yields_identical_claims():
    policies = ["shell_recipe"]
    results = set()
    for _ in range(20):
        registry = register(list(policies))
        catalog = publish(registry)
        claims = collect_setup(registry, catalog) | frozenset(catalog.providers)
        results.add(claims)
    assert len(results) == 1


def test_a_3_5_origin_assigned_by_how_a_module_entered():
    registry = register(["shell_recipe"])
    assert registry.origins["shell_recipe"] == "conftest"
    assert registry.origins["fake_shell.plugin"] == "plugin"
    assert registry.origins["fake_shell.providers"] == "plugin"
    assert registry.origin_of_package("fake_shell") == "plugin"


def test_a_3_9_cross_contributor_import_is_refused():
    with pytest.raises(CrossContributorImport) as exc_info:
        register(["bad_recipe"])
    msg = str(exc_info.value)
    assert "bad_recipe" in msg
    assert "fake_kv.providers" in msg
    assert "using=" in msg


@pytest.mark.parametrize(
    "recipe, offending",
    [
        ("nested_import_recipe", "fake_kv"),
        ("unregistered_pack_recipe", "fake_kv_alt.providers.make_store"),
        ("internals_recipe", "score.itf.core.octo"),
    ],
)
def test_a_3_9_import_statements_are_checked_wherever_they_are(recipe, offending):
    with pytest.raises(CrossContributorImport) as exc_info:
        register([recipe])
    msg = str(exc_info.value)
    assert recipe in msg and offending in msg


def test_a_3_9_every_well_behaved_fixture_imports_only_itf_core_and_itself():
    register(["fake_kv_recipe", "fake_kv_recipe_swapped", "shell_recipe"])


def test_a_3_10_using_a_function_raises_type_error(tmp_path):
    session = Session(["using_function_recipe"], run_dir=tmp_path)
    with pytest.raises(TypeError) as exc_info:
        session.resolve()
    assert "local.store" in str(exc_info.value)


def test_a_3_7_wrong_phase_capability_in_init(tmp_path):
    from score.itf.core.engine.contexts import InitContext, WrongPhase

    ctx = InitContext("policy", publish(register(["shell_recipe"])), None)
    with pytest.raises(WrongPhase):
        ctx.contract("x", gives=())


def test_a_3_7_wrong_phase_state_in_setup(tmp_path):
    from score.itf.core.engine.contexts import SetupContext, WrongPhase

    ctx = SetupContext("policy", publish(register(["shell_recipe"])))
    with pytest.raises(WrongPhase):
        ctx.scope("main").goal("itf.states.shell.open")
    with pytest.raises(WrongPhase):
        ctx.state("itf.states.shell.open", using="fake_shell.open_session")


def test_a_3_8_provides_needs_mismatch_raises_at_import():
    from score.itf.core import provides

    with pytest.raises(TypeError) as exc_info:

        @provides("some.contract", name="broken.provider", needs={"endpoint": "itf.capabilities.descriptor.endpoint"})
        def factory(config):
            pass

    assert "endpoint" in str(exc_info.value)


def test_a_3_8_delivers_uses_mismatch_raises_at_import():
    from score.itf.core import delivers

    with pytest.raises(TypeError):

        @delivers("some.state", name="broken.action", uses={"shell": "itf.capabilities.exec.shell"})
        def action():
            pass


def test_provider_shape_comes_from_its_annotations():
    from score.itf.core.engine.publish import _STAGING

    register(["shell_recipe"])
    shell = next(
        d for d in _STAGING["fake_shell.providers"] if getattr(d, "implements", "") == "itf.capabilities.exec.shell"
    )
    assert {m.name for m in shell.gives.members} >= {"run", "close"}
