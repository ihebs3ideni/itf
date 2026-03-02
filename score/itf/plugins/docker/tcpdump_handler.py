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

Runs tcpdump **inside** the container using ``exec()``.
Captures loopback traffic, internal IPC over sockets, etc.
"""

from score.itf.core.com.tcpdump import TcpDumpHandler


class InternalTcpDumpHandler(TcpDumpHandler):
    """TcpDump handler that runs tcpdump **inside** the container.

    Captures:
      - Loopback traffic (127.0.0.1)
      - Internal container network traffic
      - Any traffic visible from the container's network namespace

    Requires tcpdump to be installed in the container image.
    """

    TCPDUMP_BINARY = "/usr/sbin/tcpdump"

    def __init__(self, docker_target):
        """Initialize the handler.

        :param docker_target: The :class:`DockerTarget` instance to capture from.
        """
        self._target = docker_target

    def _build_command(
        self,
        output_path: str,
        interface: str,
        filter_expr: str,
        snapshot_length: int,
        max_packets: int | None,
        extra_args: list[str] | None,
    ) -> list[str]:
        """Build the tcpdump command line."""
        cmd = [
            self.TCPDUMP_BINARY,
            "-i", interface,
            "-w", output_path,
            "-U",  # packet-buffered output
        ]
        if snapshot_length:
            cmd += ["-s", str(snapshot_length)]
        if max_packets:
            cmd += ["-c", str(max_packets)]
        if extra_args:
            cmd.extend(extra_args)
        if filter_expr:
            cmd.extend(filter_expr.split())
        return cmd

    def start(
        self,
        output_path: str,
        *,
        interface: str = "any",
        filter_expr: str = "",
        snapshot_length: int = 0,
        max_packets: int | None = None,
        extra_args: list[str] | None = None,
    ) -> str:
        """Start tcpdump inside the container.

        :returns: The Docker exec ID.
        :rtype: str
        """
        cmd = self._build_command(
            output_path, interface, filter_expr,
            snapshot_length, max_packets, extra_args,
        )
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


# Backwards compatibility alias
DockerTcpDumpHandler = InternalTcpDumpHandler
