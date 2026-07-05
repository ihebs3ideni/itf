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
"""Host-process infrastructure -- NOT a DUT capability.

Tests run on the host anyway. This plugin publishes ``ctf/host/process``: a way
to run processes on the machine running pytest. It is *infrastructure*, always
available and target-independent. Derived DUT capabilities (e.g. ``ctf/cap/ping``)
use it to *reach* the target from the host; a target that wants to be reached
still contributes its own facts (an IP via ``ctf/cap/network``).

This would eventually graduate into ``ctf`` core; it lives here as an example
plugin for now.
"""

from __future__ import annotations

import subprocess

from ctf.contracts import provides

#: The reserved framework contract for the host-process runner.
CONTRACT = "ctf/host/process"


class HostProcess:
    """Run processes on the host (the machine running pytest)."""

    def run(self, command: str, timeout: float | None = None) -> tuple[int, bytes]:
        """Run ``command`` in a host shell; return ``(exit_code, output_bytes)``."""
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout + proc.stderr


@provides(CONTRACT)
def host_process() -> HostProcess:
    return HostProcess()


def pytest_ctf_setup(registry, config):
    registry.register(host_process)
