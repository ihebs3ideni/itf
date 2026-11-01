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
"""The provider an itf_target hands to py_itf_test."""

ItfTargetInfo = provider(
    doc = "A composition: the document, its override files, the packs it may name, the files it locates.",
    fields = {
        "document": "File: the composition (YAML).",
        "overrides": "List of Files: override files, merged by role in this order.",
        "packs": "List of py_itf_plugin targets the composition's factories come from.",
        "plan": "File: the plan written at build time.",
        "runfiles": "Runfiles: the document, overrides, included files, files and the packs' runfiles.",
        "env": "Dict of string: every `${NAME}` value the composition needs, `files` as runfiles paths included.",
    },
)
