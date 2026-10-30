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
"""Skipping unchanged artifacts must never change what ends up on disk."""

from __future__ import annotations

from score.itf.core.artifacts import write_artifacts
from score.itf.core.session import Session


def test_cached_writes_leave_the_same_files_as_a_full_write(tmp_path):
    cached = tmp_path / "a" / "run"
    session = Session(["shell_recipe"], run_dir=cached)
    session.resolve()
    session.bring_up()
    session.reach("main:itf.states.shell.open")
    session.close()

    full = tmp_path / "b" / "run"
    write_artifacts(full, session)
    names = sorted(p.name for p in full.iterdir())
    assert names == sorted(p.name for p in cached.iterdir())
    for name in names:
        assert (cached / name).read_text() == (full / name).read_text(), name
