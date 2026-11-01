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
"""A suite that requires the vendor's contract and a contract nobody defined.

`@itf.requires("power", contract="acme/power.relay@1", shape=[...])` says: the target has a role `power`, it is
an `acme/power.relay` of major 1, and it offers these members. A target whose `power` is something else, or
lacks `toggle`, deselects the test with the reason."""

import score.itf as itf


@itf.requires("power", contract="acme/power.relay@1", shape=["on", "off", "is_on"])
def test_the_relay_switches(target):
    target.power.off()
    assert not target.power.is_on()
    target.power.on()
    assert target.power.is_on()
    target.power.off()


@itf.requires("power", contract="acme/power.relay@1", shape=["toggle"])
def test_the_optional_toggle(target):
    target.power.off()
    assert target.power.toggle() is True
    target.power.off()


@itf.requires("led", contract="bench/led", shape=["light", "lit"])
def test_a_contract_without_a_definition(target):
    target.led.light(True)
    assert target.led.lit()
    target.led.light(False)
