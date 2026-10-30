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
"""`@itf.requires(token, shape=...)` against a scope with several nodes of that token."""

from __future__ import annotations

from types import SimpleNamespace

from score.itf.core.gating import Requirement, evaluate
from score.itf.core.octo import Shape

TOKEN = "files.transfer"


class _Plan:
    def __init__(self, nodes):
        self._nodes = nodes

    def tokens(self, scope):
        return tuple(sorted({n.contract for n in self._nodes.values()}))

    def names(self, scope):
        return tuple(sorted(self._nodes))

    def node(self, ref):
        return self._nodes[ref.split(".", 1)[1]]


PLAN = _Plan(
    {
        "files": SimpleNamespace(contract=TOKEN, provider="basic.files"),
        "sftp": SimpleNamespace(contract=TOKEN, provider="rich.files"),
    }
)
GIVES = {
    "basic.files": Shape.of("upload", "download"),
    "rich.files": Shape.of("upload", "download", "exists", "remove"),
}


def test_one_node_offering_the_shape_selects_the_test():
    assert evaluate(Requirement(TOKEN, ("exists", "remove")), PLAN, "s", GIVES).selected


def test_no_node_offering_the_shape_deselects_naming_the_closest_shortfall():
    decision = evaluate(Requirement(TOKEN, ("exists", "chmod")), PLAN, "s", GIVES)
    assert not decision.selected
    assert decision.reason.endswith("without member(s): chmod")
