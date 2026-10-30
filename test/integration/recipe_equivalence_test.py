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
"""A Starlark recipe and its YAML twin declare the same thing: the same ctx calls, in any order."""

from pathlib import Path

from score.itf.core.frontends.yaml_config import load_init, load_setup


class _Recorder:
    def __init__(self, calls, scope=""):
        self.calls, self._scope = calls, scope

    def __getattr__(self, verb):
        def call(*args, **kwargs):
            frozen = {k: tuple(sorted(v.items())) if isinstance(v, dict) else v for k, v in kwargs.items()}
            self.calls.add((self._scope, verb, args, tuple(sorted(frozen.items()))))

        return call

    def scope(self, name):
        return _Recorder(self.calls, name)


def _declarations(document) -> set:
    calls: set = set()
    load_setup(_Recorder(calls), document)
    load_init(_Recorder(calls), document)
    return calls


def test_docker_ssh_starlark_declares_what_docker_ssh_yaml_declares(monkeypatch):
    monkeypatch.setenv("ITF_EXTRA_MOUNT", "test/integration/suite")
    yaml = _declarations(Path("test/integration/recipes/docker_ssh.yaml"))
    starlark = _declarations(Path("test/integration/recipes/docker_ssh_starlark.itf.json"))
    assert yaml == starlark
