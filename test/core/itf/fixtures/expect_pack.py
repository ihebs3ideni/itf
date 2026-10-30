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
"""Fixtures for `tests/itf/test_expect.py`: providers using `expect()` to attach an explicit shape
to a `needs=` slot, independent of (or combined with) parameter annotations."""

from collections.abc import Iterator

from score.itf.core import expect, provides


class Endpoint:
    host: str
    port: int


class Credentials:
    user: str
    token: str


@provides(
    "itf.capabilities.exec.shell",
    name="expect_pack.explicit_shape",
    needs={"endpoint": expect("itf.capabilities.descriptor.endpoint", ("host", "port"))},
)
def explicit_shape(endpoint, config) -> Iterator[object]:
    yield object()


@provides(
    "itf.capabilities.exec.shell",
    name="expect_pack.annotation_fallback",
    needs={"creds": expect("itf.capabilities.descriptor.credentials")},
)
def annotation_fallback(creds: Credentials, config) -> Iterator[object]:
    yield object()


@provides(
    "itf.capabilities.exec.shell",
    name="expect_pack.expect_wins_over_annotation",
    needs={"endpoint": expect("itf.capabilities.descriptor.endpoint", ("host",))},
)
def expect_wins_over_annotation(endpoint: Endpoint, config) -> Iterator[object]:
    yield object()


@provides(
    "itf.capabilities.exec.shell",
    name="expect_pack.bare_string_still_works",
    needs={"endpoint": "itf.capabilities.descriptor.endpoint"},
)
def bare_string_still_works(endpoint, config) -> Iterator[object]:
    yield object()
