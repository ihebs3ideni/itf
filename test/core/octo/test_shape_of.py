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
"""`shape_of()`: structural member extraction across Protocol/dataclass/ABC/plain-class
(docs/octo-kit/30-decisions.md, shape/expect plan)."""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from score.itf.core.octo import Shape
from score.itf.core.octo.shapes import shape_of


def test_none_gives_an_empty_shape():
    assert shape_of(None) == Shape()


def test_a_shape_instance_passes_through_unchanged():
    shape = Shape.of("run", "close")
    assert shape_of(shape) is shape


def test_plain_class_extracts_annotations_and_methods():
    class Endpoint:
        host: str
        port: int

        def resolve(self): ...

    shape = shape_of(Endpoint)
    assert {m.name for m in shape.members} == {"host", "port", "resolve"}


def test_dataclass_extracts_fields_and_methods():
    @dataclass(frozen=True)
    class Credentials:
        user: str
        key_path: str

        def masked(self): ...

    shape = shape_of(Credentials)
    assert {m.name for m in shape.members} == {"user", "key_path", "masked"}


def test_abc_extracts_abstract_methods_only():
    class Transport(abc.ABC):
        @abc.abstractmethod
        def send(self, data: bytes) -> None: ...

        @abc.abstractmethod
        def recv(self) -> bytes: ...

    shape = shape_of(Transport)
    assert {m.name for m in shape.members} == {"send", "recv"}


def test_runtime_checkable_protocol_extracts_declared_members():
    @runtime_checkable
    class ExecProtocol(Protocol):
        def execute(self, command: str) -> object: ...

    shape = shape_of(ExecProtocol)
    assert {m.name for m in shape.members} == {"execute"}


def test_plain_protocol_without_runtime_checkable_still_extracts():
    class ReadOnly(Protocol):
        value: int

    shape = shape_of(ReadOnly)
    assert {m.name for m in shape.members} == {"value"}


def test_private_and_dunder_members_are_excluded():
    class Thing:
        public: str

        def __init__(self):
            self._private = 1

        def _helper(self): ...

    shape = shape_of(Thing)
    assert {m.name for m in shape.members} == {"public"}


def test_extracted_shape_is_usable_with_satisfies():
    class Endpoint:
        host: str
        port: int

    class FakeEndpoint:
        def __init__(self):
            self.host = "127.0.0.1"
            self.port = 22

    given = Shape.of(*vars(FakeEndpoint()))
    ok, missing = given.satisfies(shape_of(Endpoint))
    assert ok, missing
