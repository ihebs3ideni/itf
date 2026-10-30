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

# Recipes for //test/integration: YAML files (loaded by conftest.py from ITF_RECIPE) and Starlark
# targets (handed to py_itf_test(recipe = ...)). conftest.py also holds the code half of the policy.

exports_files(
    glob(["*.yaml"]) + ["conftest.py"],
    visibility = ["//test/integration:__pkg__"],
)

filegroup(
    name = "yaml",
    srcs = glob(["*.yaml"]),
    visibility = ["//test/integration:__pkg__"],
)
