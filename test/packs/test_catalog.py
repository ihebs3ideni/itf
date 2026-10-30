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
"""The pack catalog: every pack loads, and every expectation a consumer declares is one a provider meets.

Packs never share code, so this is where their contracts are held together: a provider's `needs` and
an action's `uses` name a token and the members they rely on (from their own Protocols); at least one
provider of that token must give those members, or the seam could never be wired.
"""

import pytest

from tools.catalog import build_catalog


@pytest.fixture(scope="module")
def catalog():
    return build_catalog.build()


def test_every_pack_entrypoint_loads(catalog):
    assert catalog["errors"] == []
    assert {p["name"] for p in catalog["packs"]} >= {"docker", "dlt", "net", "pcap", "ping", "qemu", "serial", "ssh"}


def test_every_declared_expectation_is_met_by_some_provider(catalog):
    gives: dict[str, list[set]] = {}
    for provider in catalog["providers"]:
        gives.setdefault(provider["contract"], []).append(set(provider["gives"]))
    unmet = []
    for item in catalog["providers"] + catalog["actions"]:
        for need in item.get("needs", item.get("uses", ())):
            if not any(set(need["members"]) <= offered for offered in gives.get(need["contract"], [])):
                unmet.append(f"{item['name']}.{need['slot']}: {need['contract']} with {need['members']}")
    assert not unmet, "expectations no provider meets:\n" + "\n".join(unmet)


def test_every_action_states_a_probe(catalog):
    assert [a["name"] for a in catalog["actions"] if not a["probe"]] == []
