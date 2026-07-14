# *******************************************************************************
# Copyright (c) 2025-2026 Contributors to the Eclipse Foundation
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
"""QEMU-specific startup checks.

Only verifies what the QEMU target plugin itself owns:
- The VM is reachable via ping (since the target provides itf/net/ip_address).

SSH/SFTP connectivity is verified by the SSH capability plugin's own health check.
"""

import logging

from score.itf.plugins.capabilities.ping.ping import ping

logger = logging.getLogger(__name__)

IP_ADDRESS_CONTRACT = "itf/net/ip_address"


def check_qemu_reachable(dut, timeout: int = 30):
    """Verify the QEMU VM is network-reachable via ping.

    Called from the plugin's ``pytest_ctf_health_check`` hook.
    Only runs if the DUT actually provides an IP address.
    """
    if not dut.available(IP_ADDRESS_CONTRACT):
        return

    ip = dut.require(IP_ADDRESS_CONTRACT)
    result = ping(ip, timeout=timeout)
    assert result, f"QEMU target at {ip} is not reachable within {timeout}s"
    logger.info(f"QEMU health check: ping {ip} OK")
