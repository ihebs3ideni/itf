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
"""The recipe as `itf_setup` and `itf_init`: loaded by `py_itf_test(recipe = ...)`.

It implements only the two declarative hooks, from the generated document. The test's root
conftest keeps everything that is code (`itf_verify`, `itf_teardown`, fixtures, bench-local
actions) and, if it also implements `itf_setup`/`itf_init`, adds to the recipe or overrides it: the
root conftest outranks every plugin.
"""

from score.itf.core import hookimpl, load_init, load_setup, recipe_document


@hookimpl
def itf_setup(ctx):
    load_setup(ctx, recipe_document())


@hookimpl
def itf_init(ctx):
    load_init(ctx, recipe_document())
