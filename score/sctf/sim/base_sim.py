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
import os
import signal
import logging
import score.sctf.config as sctf_config
from score.sctf.sandbox import Process, NoSandbox, BwrapSandbox
from score.sctf.exception import SctfAssertionError

# Broken
from score.sctf.sim.state import ApplicationState


logger = logging.getLogger(__name__)


class BaseSim:
    # TODO: Relax the number of attributes - perhaps encapsulate in a struct?
    # pylint: disable=too-many-instance-attributes
    # pylint: disable=too-many-arguments

    _execution_manager = None

    @staticmethod
    def register_execution_manager(execution_manager):
        BaseSim._execution_manager = execution_manager

    def _wait_until_running(self):
        BaseSim._execution_manager.assert_reported_state(self, ApplicationState.Running)

    def __init__(
        self,
        environment,
        binary_path,
        args,
        cwd="/",
        use_sandbox=True,
        wait_on_exit=False,
        wait_timeout=sctf_config.TEST_TIMEOUT_S,
        extra_mount_list=None,
        enforce_clean_shutdown=False,  # TODO: dmsim does not exit gracefully, to be fixed
        expected_exit_code=0,
    ):
        self.environment = environment
        self.binary_path = binary_path
        self.args = args
        self.process = None
        self.cwd = cwd

        self.ret_code = None

        self.use_sandbox = use_sandbox
        self._wait_on_exit = wait_on_exit
        self._wait_timeout = wait_timeout

        self.extra_mount_list = extra_mount_list
        self.enforce_clean_shutdown = enforce_clean_shutdown
        self.expected_exit_code = expected_exit_code

    def __enter__(self):
        if self.use_sandbox:
            sandbox = BwrapSandbox(self.environment, self.extra_mount_list)
        else:
            sandbox = NoSandbox(self.environment)

        self.process = Process(self.binary_path, self.args, sandbox, self.cwd)
        self.process.start()
        return self

    def __exit__(self, exception_type, exception_value, traceback):
        self.ret_code = self._handle_process_exit()
        logger.debug(f"Application [{os.path.basename(self.binary_path)}] exit code: [{self.ret_code}]")
        self._check_process_exit_code()

    def _handle_process_exit(self):
        if self._wait_on_exit:
            return self.process.wait(self._wait_timeout)
        # don't wait for process natural finish, just terminate it
        if self.process.is_running():
            return self.process.stop()
        return 0

    def pid(self):
        return self.process.pid()

    def _check_process_exit_code(self):
        signal_base = 128
        acceptable_exit_codes = {
            0,
            signal_base + signal.SIGTERM,
            self.expected_exit_code,
        }  # SIGTERM considered OK, because it is how SCTF stops processes

        # If clean shutdown is not enforced, then SIGKILL is an acceptable exit code
        if not self.enforce_clean_shutdown:
            acceptable_exit_codes.add(signal_base + signal.SIGKILL)

        if self.ret_code not in acceptable_exit_codes:
            assert self.ret_code != 55, "Sanitizers failed"
            assert self.ret_code != signal_base + signal.SIGKILL, (
                f"Application [{self.binary_path}] exit code: [{self.ret_code}] "
                f"indicates it was stopped with SIGKILL, so it did not shut down gracefully, but enforce_clean_shutdown is flagged as True"
            )
            assert self.ret_code != signal_base + signal.SIGSEGV, (
                f"Application [{self.binary_path}] exit code: [{self.ret_code}] indicates SIGSEGV occurred."
            )
            assert self.ret_code != signal_base + signal.SIGABRT, (
                f"Application [{self.binary_path}] exit code: [{self.ret_code}] indicates SIGABRT occurred."
            )
            raise SctfAssertionError(
                f"Application [{self.binary_path}] exit code: [{self.ret_code}] indicates an error."
            )
