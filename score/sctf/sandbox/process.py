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
"""Responsible for handling process lifetime."""

import logging
import psutil
import score.sctf.config as sctf_config
from score.sctf.exception import SctfRuntimeError


logger = logging.getLogger(__name__)


class Process:
    def __init__(self, path, args, sandbox, cwd="/"):
        self.path = path
        self.args = args
        self.sandbox = sandbox
        self.cwd = cwd

        # Received from the sandbox upon process startup
        self.parent_proc = None
        self.child_proc = None
        self.stdout_thread = None
        self.stderr_thread = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, type_, value, traceback):
        self.stop()

    def start(self):
        """
        Start a new process under settings provided in the constructor.
        :return: a tuple, containing parent process (bwrap), wrapped process, stdout thread, stderr thread handles
        """
        self.parent_proc, self.child_proc, self.stdout_thread, self.stderr_thread = self.sandbox.start(
            self.path, self.args, self.cwd
        )
        logger.info(f"Created process {self.parent_proc}")
        if self.child_proc:
            logger.info(f"Created child process {self.child_proc}")
        else:
            logger.debug(f"Child process {self.path} is None, assuming it has already finished")

    def _stop_child(self, callable_):
        try:
            self.child_proc.terminate()
            for _ in range(5):
                try:
                    self.child_proc.wait(1)
                    break
                except psutil.TimeoutExpired:
                    try:
                        if callable_:
                            callable_()
                    except Exception:
                        logger.exception("Caught an unexpected exception")
        except psutil.NoSuchProcess as ex:
            logger.warning(
                f"Exception while stopping child process: {ex}, assuming process terminated already, continuing."
            )
        finally:
            if self.child_proc.is_running():
                logger.error(f"Application {self.path} did not terminate properly, sending SIGKILL.")
                self.child_proc.kill()
                self.child_proc.wait()

        # Parent process should end once the child process is finished - it will propagate the child process exit code
        return self.parent_proc.wait(sctf_config.TIMEOUT_S)

    def _stop_parent(self):
        try:
            self.parent_proc.terminate()
            return self.parent_proc.wait(sctf_config.TIMEOUT_S)
        except psutil.TimeoutExpired:
            logger.error(
                f"Application {self.path} did not stop after {sctf_config.TIMEOUT_S} sec on SIGTERM, sending SIGKILL."
            )
            self.parent_proc.kill()
            return self.parent_proc.wait()

    def stop(self, callable_=None):
        """Terminates application

        First a SIGTERM is issued, application should close itself,
        if that does not happen a SIGKILL is sent to force app exit.

        After SIGTERM the arg callable will be called, so arbitrary
        functionality could be run in the shutdown phase.

        Returns the exit code of the wrapped process.

        :return: exit code of the stopped, wrapped process
        """
        # Child process available: terminate or kill it, then get the return code from the parent
        if self.child_proc:
            ret_code = self._stop_child(callable_)
        # Child process unavailable, possibly already stopped: terminate or kill parent, then get the return code
        else:
            ret_code = self._stop_parent()

        self.stdout_thread.join()
        self.stderr_thread.join()

        return ret_code

    def pid(self):
        """
        Return the process id of the wrapped process.
        :return: process id of the wrapped process
        :raise: SctfRuntimeError if the child process (the same process in case of NoSandbox) is not set
        """
        if self.child_proc:
            return self.child_proc.pid
        raise SctfRuntimeError("Child process is None, could not determine PID")

    def wait(self, timeout_s=sctf_config.TIMEOUT_S):
        """
        Waits for the wrapped process to finish, returning its exit code.
        :param timeout_s: maximum wait duration for the process finish
        :return: process exit code
        :raise: SctfRuntimeError if target process not exists or in case of timeout
        """
        pid = None
        try:
            if self.child_proc:
                pid = self.child_proc.pid
                self.child_proc.wait(timeout_s)

            pid = self.parent_proc.pid
            return self.parent_proc.wait(timeout_s)
        except psutil.TimeoutExpired as original_exception:
            raise SctfRuntimeError(
                f"Waiting for process with PID [{pid}] to terminate timed out after {timeout_s} seconds"
            ) from original_exception
        except psutil.NoSuchProcess as original_exception:
            raise SctfRuntimeError(f"Process with PID [{pid}] no longer exists") from original_exception

    def is_running(self):
        """
        Return wrapped process `is_running` state. If the process has finished, the returned value will be False.
        :return: boolean value whether the wrapped process is running or not
            (if target process is not setup properly, False is returned - assuming it has already finished and could not be found)
        """
        if self.child_proc:
            return self.child_proc.is_running()
        return False
