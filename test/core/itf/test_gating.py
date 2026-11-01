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
"""`@itf.requires`: a test is deselected, with a reason, when the role is missing, is another contract or lacks members."""

import kv_parts
import pytest

import score.itf as itf
from score.itf.core import Session
from score.itf.core.gating import Requirement, get_requirements

COMPOSITION = """
capabilities:
  store: project.store
  reader: project.view
  slim: project.slim_view
"""


@pytest.fixture
def session(tmp_path):
    return Session([kv_parts], target=COMPOSITION, plan_only=True, run_dir=tmp_path / "run").resolve()


def decide(session, *requirements):
    return session.select({"t": tuple(requirements)})["t"]


def test_requires_collects_requirements_on_the_test():
    @itf.requires("store")
    @itf.requires("reader", contract="kv.view@1", shape=["read"])
    def test_something(): ...

    assert get_requirements(test_something) == (
        Requirement("reader", "kv.view", ("read",), None, 1),
        Requirement("store"),
    )


def test_requires_takes_a_role_name():
    with pytest.raises(TypeError, match="role name"):
        itf.requires(None)
    with pytest.raises(TypeError, match="list of member names"):
        itf.requires("store", shape="get")


def test_a_present_role_selects_the_test(session):
    assert decide(session, Requirement("store")).selected


def test_a_missing_role_deselects_with_a_reason_naming_the_roles(session):
    decision = decide(session, Requirement("command"))
    assert not decision.selected
    assert decision.reason == "target has no role 'command'; roles: reader, slim, store"


def test_another_contract_deselects(session):
    decision = decide(session, Requirement("store", contract="kv.view"))
    assert not decision.selected
    assert "is 'kv.store', the test requires 'kv.view'" in decision.reason
    assert decide(session, Requirement("store", contract="kv.store")).selected


def test_missing_members_deselect(session):
    assert decide(session, Requirement("reader", shape=("read",))).selected
    decision = decide(session, Requirement("slim", shape=("read",)))
    assert not decision.selected
    assert "lacks member(s): read" in decision.reason


def test_a_major_the_factory_does_not_offer_deselects(tmp_path):
    session = Session(
        [kv_parts],
        target="capabilities:\n  store: project.store\n  reader: project.view_v1\n",
        plan_only=True,
        run_dir=tmp_path / "run",
    ).resolve()
    assert decide(session, Requirement("reader", "kv.view", None, None, 1)).selected
    decision = decide(session, Requirement("reader", "kv.view", None, None, 2))
    assert not decision.selected and "offers @1, the test requires @2" in decision.reason


def test_a_scope_is_checked_instead_of_the_root(tmp_path):
    session = Session(
        [kv_parts],
        target="capabilities:\n  store: project.store\nscopes:\n  gw:\n    capabilities:\n      other: project.store\n",
        plan_only=True,
        run_dir=tmp_path / "run",
    ).resolve()
    assert decide(session, Requirement("other", scope="gw")).selected
    assert not decide(session, Requirement("other")).selected
    decision = decide(session, Requirement("store", scope="nowhere"))
    assert decision.reason == "target has no scope 'nowhere'"


def test_every_requirement_must_hold(session):
    assert not decide(session, Requirement("store"), Requirement("command")).selected
