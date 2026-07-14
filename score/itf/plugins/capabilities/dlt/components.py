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

from __future__ import annotations

import logging
from contextlib import contextmanager

from score.itf.plugins.capabilities.dlt.dlt_receive import protocol_arguments


logger = logging.getLogger(__name__)


class DltReceiver:
    """Thin wrapper around an AsyncProcess that tracks DLT output path."""

    def __init__(self, proc, dlt_file=None):
        self._proc = proc
        self.dlt_file = dlt_file

    def __getattr__(self, name):
        return getattr(self._proc, name)


class DltOnTargetComponent:
    """Contract-backed factory for running dlt-receive on the target."""

    def __init__(self, exec_interface, file_transfer_interface, local_binary: str):
        self._exec = exec_interface
        self._files = file_transfer_interface
        self._local_binary = local_binary
        self._remote_path = "/tmp/dlt-receive"
        self._output_dir = "/tmp"
        self._receivers = []
        self._counter = 0

        self._files.upload(self._local_binary, self._remote_path)
        self._exec.execute(f"chmod +x {self._remote_path}")

    @contextmanager
    def __call__(
        self,
        protocol,
        host_ip="127.0.0.1",
        target_ip="127.0.0.1",
        multicast_ips=None,
        print_to_stdout=True,
        output_file=None,
    ):
        self._counter += 1
        dlt_file = output_file or f"{self._output_dir}/dlt-receive-{self._counter}.dlt"

        args = protocol_arguments(protocol, host_ip, target_ip, multicast_ips or [])
        args += ["-o", dlt_file]
        if print_to_stdout:
            args += ["-a", "--stdout-flush"]

        proc = self._exec.execute_async(self._remote_path, args=args)
        receiver = DltReceiver(proc, dlt_file=dlt_file)
        self._receivers.append(proc)
        try:
            yield receiver
        finally:
            if proc.is_running():
                proc.stop()

    def stop_all(self):
        for proc in self._receivers:
            try:
                if proc.is_running():
                    proc.stop()
            except Exception:
                logger.warning("Failed to stop on-target dlt-receive", exc_info=True)
