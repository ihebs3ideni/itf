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
"""No-sandbox execution environment.

Runs binaries directly on the host with no isolation — equivalent to the
original ``score.sctf.sandbox.NoSandbox``.  Useful for debugging or for
environments where neither Docker nor Bubblewrap is available.
"""

import logging
import os
import shutil
import subprocess
import threading

import psutil

from score.itf.core.environment.base import Environment, ProcessHandle

logger = logging.getLogger(__name__)

LINE_BUFFER = ["/usr/bin/stdbuf", "-oL"]

_TIMEOUT_S = 15.0


def _async_log(fd, logger_name: str) -> None:
    log = logging.getLogger(logger_name)
    try:
        for line in fd:
            log.info(line.rstrip("\n"))
    except ValueError:
        pass


class NoopEnvironment(Environment):
    """Run binaries directly on the host — no sandboxing.

    Parameters:
        timeout: Default stop-process timeout in seconds.
    """

    def __init__(self, *, timeout: float = _TIMEOUT_S):
        self._timeout = timeout
        self._handles: list[ProcessHandle] = []

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def setup(self) -> None:
        """Nothing to prepare."""

    def teardown(self) -> None:
        for h in list(self._handles):
            try:
                if self.is_process_running(h):
                    self.stop_process(h)
            except Exception:  # noqa: BLE001
                logger.debug("Ignoring error during teardown", exc_info=True)
        self._handles.clear()

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def execute(self, path: str, args: list[str], cwd: str = "/") -> ProcessHandle:
        if not (os.path.isfile(path) and os.access(path, os.X_OK)):
            raise RuntimeError(f"File is not a valid executable: {path}")

        cmd = LINE_BUFFER + [path] + args
        proc = psutil.Popen(
            cmd,
            bufsize=0,
            universal_newlines=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            close_fds=True,
        )
        logger_name = os.path.basename(path)
        stdout_thread = self._start_logging_thread(proc.stdout, logger_name)
        stderr_thread = self._start_logging_thread(proc.stderr, logger_name)

        handle = ProcessHandle(
            pid=proc.pid,
            parent=proc,
            child=proc,  # Same process — no wrapper
            stdout_thread=stdout_thread,
            stderr_thread=stderr_thread,
        )
        self._handles.append(handle)
        return handle

    def stop_process(self, handle: ProcessHandle, timeout: float | None = None) -> int:
        timeout = timeout if timeout is not None else self._timeout
        proc = handle.parent

        # If the process already finished, just collect its exit code.
        if not proc.is_running():
            exit_code = proc.wait(timeout=0)
        else:
            try:
                proc.terminate()
                exit_code = proc.wait(timeout)
            except psutil.TimeoutExpired:
                logger.error("Process did not stop in %ss, sending SIGKILL", timeout)
                proc.kill()
                exit_code = proc.wait()

        if handle.stdout_thread:
            handle.stdout_thread.join(timeout=5)
        if handle.stderr_thread:
            handle.stderr_thread.join(timeout=5)

        handle.exit_code = exit_code
        if handle in self._handles:
            self._handles.remove(handle)
        return exit_code

    def is_process_running(self, handle: ProcessHandle) -> bool:
        if handle.parent:
            return handle.parent.is_running()
        return False

    # ------------------------------------------------------------------
    # File transfer (simple host-to-host copy)
    # ------------------------------------------------------------------

    def copy_to(self, host_path: str, env_path: str) -> None:
        os.makedirs(os.path.dirname(env_path), exist_ok=True)
        if os.path.isdir(host_path):
            shutil.copytree(host_path, env_path, dirs_exist_ok=True)
        else:
            shutil.copy2(host_path, env_path)

    def copy_from(self, env_path: str, host_path: str) -> None:
        os.makedirs(os.path.dirname(host_path), exist_ok=True)
        if os.path.isdir(env_path):
            shutil.copytree(env_path, host_path, dirs_exist_ok=True)
        else:
            shutil.copy2(env_path, host_path)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _start_logging_thread(stream, logger_name: str) -> threading.Thread:
        t = threading.Thread(target=_async_log, args=(stream, logger_name), daemon=True)
        t.start()
        return t
