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
"""Collected by every itf_recipe's `<name>_plan` test, which runs with --itf-plan: the session
resolves both gates on the recipe and stops before any test runs; a diagnostic fails it."""


def test_recipe_resolves():
    """Never runs: --itf-plan exits after resolution and gating."""
