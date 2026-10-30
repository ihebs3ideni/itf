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
"""`using=` given a function object instead of a name (A-3.10). The provider is the recipe's own,
so no import rule is broken; the name-only rule of `using=` still applies."""

from score.itf.core import hookimpl, provides


@provides("kv.store", name="local.store")
def local_store(config):
    return {}


@hookimpl
def itf_setup(ctx):
    ctx.scope("main").add("store", using=local_store)


@hookimpl
def itf_init(ctx):
    ctx.scope("main").goal("kv_seeded")
