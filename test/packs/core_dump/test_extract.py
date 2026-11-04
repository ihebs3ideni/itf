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
"""Core dump extraction through the command and file-transfer contracts."""

from score.itf.packs.core_dump.extract import LIST_CORES, extract_core_dumps


class _Command:
    def __init__(self, listing: str):
        self.listing = listing
        self.ran = []

    def exec(self, command, timeout=30.0):
        self.ran.append(command)
        return 0, self.listing


class _Files:
    def __init__(self, failing=()):
        self.downloaded = []
        self.failing = failing

    def download(self, remote, local):
        if remote in self.failing:
            raise OSError("gone")
        self.downloaded.append((remote, local))


def test_found_cores_are_mirrored_under_the_output_dir(tmp_path):
    command, files = _Command("/tmp/core.123\n/opt/app/app.core\n"), _Files()
    extracted = extract_core_dumps(command, files, str(tmp_path))
    assert command.ran == [LIST_CORES]
    assert files.downloaded == [
        ("/tmp/core.123", str(tmp_path / "tmp/core.123")),
        ("/opt/app/app.core", str(tmp_path / "opt/app/app.core")),
    ]
    assert extracted == [local for _, local in files.downloaded]


def test_a_failed_download_does_not_stop_the_others(tmp_path):
    files = _Files(failing={"/tmp/core.1"})
    extracted = extract_core_dumps(_Command("/tmp/core.1\n/tmp/core.2\n"), files, str(tmp_path))
    assert extracted == [str(tmp_path / "tmp/core.2")]


def test_paths_escaping_the_output_dir_are_skipped(tmp_path):
    files = _Files()
    assert extract_core_dumps(_Command("/../../etc/passwd\n"), files, str(tmp_path)) == []
    assert files.downloaded == []
