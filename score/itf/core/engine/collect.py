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
"""Drive `itf_setup`/`itf_init` per registered module, with per-module origin and a fresh
context each, then drain into one frozenset (order-independent, docs/octo-kit/11-spec-itf-engine.md §5).
"""

from __future__ import annotations

from .contexts import InitContext, SetupContext


def collect_setup(registry, catalog) -> frozenset:
    claims: set = set()
    for hi in registry.pm.hook.itf_setup.get_hookimpls():
        origin = registry.origin_of(hi.plugin)
        ctx = SetupContext(origin, catalog)
        hi.function(ctx)
        claims |= ctx._drain()
    return frozenset(claims)


def collect_init(registry, catalog, target_plan) -> frozenset:
    claims: set = set()
    for hi in registry.pm.hook.itf_init.get_hookimpls():
        origin = registry.origin_of(hi.plugin)
        ctx = InitContext(origin, catalog, target_plan)
        hi.function(ctx)
        claims |= ctx._drain()
    return frozenset(claims)
