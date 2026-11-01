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
"""Conformance of the observe area: logs and captures."""

import os

from score.itf.contracts.conformance import check, expect

LOGS = "observe.logs"
CAPTURE = "observe.capture"


@check()
def lines_is_a_list_of_messages(node):
    lines = node.lines()
    expect(isinstance(lines, list), f"lines() returned {type(lines).__name__}, expected a list")


@check(shape=("filter",))
def filter_with_unknown_ids_is_empty(node):
    result = node.filter(apid="\x01nope", ctid="\x01nope")
    expect(result == [], f"filter() with ids no message has returned {len(result)} messages")


@check(shape=("filter",))
def filter_without_criteria_never_returns_more_than_lines(node):
    before = len(node.lines())
    got = len(node.filter())
    expect(got >= before, f"filter() returned {got} messages, fewer than the {before} lines() had before")


CHECKS = {
    LOGS: [
        lines_is_a_list_of_messages,
        filter_with_unknown_ids_is_empty,
        filter_without_criteria_never_returns_more_than_lines,
    ],
}


@check()
def a_capture_is_running(node):
    expect(node.running(), "running() is false although capture.running holds")


@check(shape=("path",))
def the_capture_has_a_file(node):
    expect(os.path.exists(str(node.path)), f"the capture file {node.path} does not exist")


CHECKS[CAPTURE] = [a_capture_is_running, the_capture_has_a_file]
