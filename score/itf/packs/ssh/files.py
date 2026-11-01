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
"""File transfer over SFTP on the session connection (`sftp.files`)."""

from __future__ import annotations

import logging

import os
import shlex
import stat
import paramiko

from .command import Shell

logger = logging.getLogger(__name__)


class SftpFiles:
    """`files` over SFTP on the session's connection, plus directory helpers."""

    def __init__(self, shell: Shell):
        self.shell = shell

    def _sftp(self) -> paramiko.SFTPClient:
        return self.shell.client().open_sftp()

    def upload(self, local_path: str, remote_path: str) -> None:
        logger.info("sftp upload: %s -> %s", local_path, remote_path)
        if not os.path.isfile(local_path):
            raise FileNotFoundError(local_path)
        remote_dir = os.path.dirname(remote_path)
        if remote_dir:
            code, out = self.shell.exec(f"test -d {shlex.quote(remote_dir)} || mkdir -p {shlex.quote(remote_dir)}")
            if code != 0:
                raise RuntimeError(f"could not create remote directory {remote_dir}: {out}")
        with self._sftp() as sftp:
            sftp.put(local_path, remote_path)

    def download(self, remote_path: str, local_path: str) -> None:
        logger.info("sftp download: %s -> %s", remote_path, local_path)
        os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
        with self._sftp() as sftp:
            sftp.get(remote_path, local_path)
            remote = sftp.stat(remote_path)
        os.utime(local_path, (remote.st_atime, remote.st_mtime))

    def exists(self, remote_path: str) -> bool:
        with self._sftp() as sftp:
            try:
                sftp.stat(remote_path)
                return True
            except FileNotFoundError:
                return False

    def listdir(self, remote_path: str) -> list[str]:
        with self._sftp() as sftp:
            return sorted(sftp.listdir(remote_path))

    def remove(self, remote_path: str) -> None:
        with self._sftp() as sftp:
            sftp.remove(remote_path)

    def upload_dir(self, local_dir: str, remote_dir: str) -> None:
        for dirpath, _, filenames in os.walk(local_dir):
            relative = os.path.relpath(dirpath, local_dir)
            for filename in filenames:
                self.upload(
                    os.path.join(dirpath, filename), os.path.normpath(os.path.join(remote_dir, relative, filename))
                )

    def download_dir(self, remote_dir: str, local_dir: str) -> None:
        with self._sftp() as sftp:
            pending = [remote_dir]
            while pending:
                current = pending.pop()
                for entry in sftp.listdir_attr(current):
                    remote = f"{current.rstrip('/')}/{entry.filename}"
                    if stat.S_ISDIR(entry.st_mode):
                        pending.append(remote)
                    else:
                        self.download(remote, os.path.join(local_dir, os.path.relpath(remote, remote_dir)))
