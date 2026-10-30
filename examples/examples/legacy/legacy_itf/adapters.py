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
"""The original Ssh and Sftp objects, presented over pack nodes (`ssh.shell`, `sftp.files`)."""

COMMAND_TIMEOUT = 30
MAX_EXEC_TIME = 180


class LegacySsh:
    """`target.ssh()`: a context manager with `execute_command` / `execute_command_output`."""

    def __init__(self, shell):
        self._shell = shell

    def __enter__(self):
        if not self._shell.is_connected():
            self._shell.connect()
        return self

    def __exit__(self, *exc):
        return False

    def get_paramiko_client(self):
        return self._shell.client()

    def execute_command_output(
        self,
        cmd,
        timeout=COMMAND_TIMEOUT,
        max_exec_time=MAX_EXEC_TIME,
        logger_in=None,
        verbose=True,
        separate_stderr=True,
    ):
        return self._shell.exec_lines(
            cmd, timeout=timeout, max_exec_time=max_exec_time, separate_stderr=separate_stderr, log=verbose
        )

    def execute_command(self, cmd, timeout=COMMAND_TIMEOUT, max_exec_time=MAX_EXEC_TIME, logger_in=None, verbose=True):
        return self.execute_command_output(cmd, timeout, max_exec_time, logger_in, verbose)[0]


class LegacySftp:
    """`target.sftp()`: a context manager with the original method names."""

    def __init__(self, files):
        self._files = files

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def upload(self, local_path, remote_path, verbose=True):
        self._files.upload(local_path, remote_path)

    def download(self, remote_path, local_path, verbose=True):
        self._files.download(remote_path, local_path)

    def list_dirs_and_files_name(self, remote_path):
        return self._files.listdir(remote_path)

    def file_exists(self, remote_path):
        return self._files.exists(remote_path)

    def remove(self, path):
        self._files.remove(path)

    def upload_dir(self, local_path, remote_path, verbose=True):
        self._files.upload_dir(local_path, remote_path)

    def download_dir(self, remote_path, local_path, verbose=True):
        self._files.download_dir(remote_path, local_path)
