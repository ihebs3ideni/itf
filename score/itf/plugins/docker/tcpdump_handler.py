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
"""TcpDump handler implementation for Docker targets.

Uses ``exec()`` to start tcpdump inside the container, ``kill_exec()`` /
``wait_exec()`` to stop it, and ``copy_from()`` to retrieve the pcap.
"""

from score.itf.core.com.tcpdump import TcpDumpHandler


class DockerTcpDumpHandler(TcpDumpHandler):
    """TcpDump handler for Docker containers.

    Uses ``exec()`` to start tcpdump, ``kill_exec()`` / ``wait_exec()``
    to stop it, and ``copy_from()`` to retrieve the pcap.
    """

    def __init__(self, docker_target):
        """Initialize the handler.

        :param docker_target: The :class:`DockerTarget` instance to capture from.
        """
        self._target = docker_target

    def start(self, cmd):
        """Start tcpdump with *cmd* on the container.

        :param cmd: The full tcpdump command line (list of strings).
        :returns: The Docker exec ID.
        :rtype: str
        """
        return self._target.exec(cmd, detach=True)

    def stop(self, handle):
        """Stop the tcpdump process.

        :param handle: The exec ID returned by :meth:`start`.
        """
        self._target.kill_exec(handle, signal=15)
        self._target.wait_exec(handle, timeout=5.0)

    def retrieve(self, target_pcap_path, host_path):
        """Copy the pcap file from the container to the host.

        :param target_pcap_path: Path to the pcap file inside the container.
        :param host_path: Destination path on the host.
        """
        self._target.copy_from(target_pcap_path, host_path)
