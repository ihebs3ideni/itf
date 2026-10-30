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
"""A-3.6: every OCTO diagnostic code has exactly one render template."""

from score.itf.core.octo import CODES
from score.itf.core.engine.render import TEMPLATES
from score.itf.core.octo.diagnostics import Diagnostic


def test_a_3_6_every_code_has_a_template():
    missing = CODES - set(TEMPLATES)
    assert not missing, f"codes with no template: {sorted(missing)}"


def test_a_3_6_templates_name_gate_and_hook():
    d = Diagnostic("NO_PROVIDER", "main.thing#slot", 1, ())
    from score.itf.core.engine.render import render

    text = render([d], gate=1, hook="itf_setup")
    assert "Gate 1 · itf_setup" in text
    assert "Fix:" in text
