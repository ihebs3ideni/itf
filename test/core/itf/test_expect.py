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
"""`expect()`: an explicit shape on a `needs=`/`uses=` slot, independent of or combined with a
parameter's own type annotation (shape/expect plan step 2, `docs/octo-kit/30-decisions.md`).

Also `ctx.expect()`: the policy-level, additive counterpart (step 3) — a shape every node offering
a contract must satisfy, regardless of which consumer asked for it.
"""

from __future__ import annotations

import pytest

from score.itf.core.engine.contexts import SetupContext, WrongPhase, InitContext
from score.itf.core.engine.publish import _STAGING
from score.itf.core.octo import Shape, ShapeExpectationClaim


def _descriptor(module, name: str):
    return next(d for d in _STAGING[module.__name__] if d.name == name)


def test_expect_shape_is_used_as_the_need_s_expected_shape():
    import expect_pack

    desc = _descriptor(expect_pack, "expect_pack.explicit_shape")
    [need] = desc.needs
    assert need.slot == "endpoint"
    assert need.contract == "itf.capabilities.descriptor.endpoint"
    assert {m.name for m in need.expected.members} == {"host", "port"}


def test_expect_with_no_shape_falls_back_to_the_parameter_s_annotation():
    import expect_pack

    desc = _descriptor(expect_pack, "expect_pack.annotation_fallback")
    [need] = desc.needs
    assert need.slot == "creds"
    assert need.contract == "itf.capabilities.descriptor.credentials"
    assert {m.name for m in need.expected.members} == {"user", "token"}


def test_expect_s_own_shape_wins_over_the_parameter_s_annotation():
    import expect_pack

    desc = _descriptor(expect_pack, "expect_pack.expect_wins_over_annotation")
    [need] = desc.needs
    assert {m.name for m in need.expected.members} == {"host"}  # expect()'s shape, not Endpoint's


def test_a_bare_string_need_still_works_unchanged():
    import expect_pack

    desc = _descriptor(expect_pack, "expect_pack.bare_string_still_works")
    [need] = desc.needs
    assert need.slot == "endpoint"
    assert need.contract == "itf.capabilities.descriptor.endpoint"
    assert need.expected.members == frozenset()


def test_ctx_expect_is_setup_phase_only():
    setup_ctx = SetupContext("policy", catalog=None)
    setup_ctx.expect("itf.capabilities.descriptor.endpoint", ("host", "port"))
    [claim] = setup_ctx._drain()
    assert claim == ShapeExpectationClaim(
        contract="itf.capabilities.descriptor.endpoint", shape=Shape.of("host", "port"), origin="policy"
    )

    init_ctx = InitContext("policy", catalog=None, target_plan=None)
    with pytest.raises(WrongPhase):
        init_ctx.expect("itf.capabilities.descriptor.endpoint", ("host", "port"))


def test_ctx_expect_accepts_a_plain_class_too():
    class Endpoint:
        host: str
        port: int

    setup_ctx = SetupContext("policy", catalog=None)
    setup_ctx.expect("itf.capabilities.descriptor.endpoint", Endpoint)
    [claim] = setup_ctx._drain()
    assert {m.name for m in claim.shape.members} == {"host", "port"}


def test_ctx_expect_with_no_shape_is_a_no_op_requirement():
    setup_ctx = SetupContext("policy", catalog=None)
    setup_ctx.expect("itf.capabilities.descriptor.endpoint")
    [claim] = setup_ctx._drain()
    assert claim.shape == Shape()
