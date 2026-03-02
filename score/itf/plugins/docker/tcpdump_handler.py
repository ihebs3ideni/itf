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
"""TcpDump handler implementations for Docker targets.

Provides two handlers:

- :class:`InternalTcpDumpHandler` — runs tcpdump **inside** the container.
  Captures loopback traffic, internal IPC over sockets, etc.

- :class:`ExternalTcpDumpHandler` — runs tcpdump on the **host** veth interface.
  Captures traffic entering/leaving the container without requiring tcpdump
  installed inside the container.
"""

import logging
import os
import shutil
import subprocess
import time

from score.itf.core.com.tcpdump import TcpDumpHandler
from score.itf.core.process.process_wrapper import ProcessWrapper

logger = logging.getLogger(__name__)


def _check_tcpdump_capture(tcpdump_bin: str) -> bool:
    """Test if a tcpdump binary can capture on docker0.

    Actually attempts a brief capture to verify raw packet capture works
    in the current execution environment. This handles:
    - Missing binary
    - Missing CAP_NET_RAW capability
    - Bazel sandbox restrictions
    - Running as root (always works)

    :param tcpdump_bin: Path to tcpdump binary to test.
    :returns: True if capture works, False otherwise.
    """
    if not tcpdump_bin or not os.path.exists(tcpdump_bin):
        return False

    # Check if docker0 exists (Docker must be running)
    if not os.path.exists("/sys/class/net/docker0"):
        logger.debug("docker0 interface not found")
        return False

    try:
        result = subprocess.run(
            [tcpdump_bin, "-i", "docker0", "-c", "1", "-w", "/dev/null"],
            capture_output=True,
            text=True,
            timeout=0.5,
        )
        if "permission" in result.stderr.lower():
            logger.debug("%s: capture permission denied", tcpdump_bin)
            return False
        return True
    except subprocess.TimeoutExpired as e:
        stderr = e.stderr.decode() if e.stderr else ""
        if "permission" in stderr.lower():
            logger.debug("%s: capture permission denied", tcpdump_bin)
            return False
        # Timeout with no permission error = capture started successfully
        return True
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


def can_capture_on_host(tcpdump_bin: str) -> bool:
    """Check if the given tcpdump binary can capture on host interfaces.

    :param tcpdump_bin: Path to the tcpdump binary to test.
    :returns: True if capture is possible, False otherwise.
    """
    return _check_tcpdump_capture(tcpdump_bin)


# ---------------------------------------------------------------------------
# Internal handler (tcpdump inside container)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# External handler (tcpdump on host veth)
# ---------------------------------------------------------------------------


def _get_container_veth(container_id: str) -> str:
    """Find the host-side veth interface linked to a container's eth0.

    :param container_id: The Docker container ID (short or full).
    :returns: The veth interface name on the host (e.g. ``veth1234abc``).
    :raises RuntimeError: If the veth interface cannot be determined.
    """
    # Get the ifindex of eth0 inside the container's network namespace
    result = subprocess.run(
        ["docker", "exec", container_id, "cat", "/sys/class/net/eth0/iflink"],
        capture_output=True,
        text=True,
        check=True,
    )
    iflink = result.stdout.strip()

    # Find the interface on the host with that ifindex
    for iface in os.listdir("/sys/class/net"):
        try:
            with open(f"/sys/class/net/{iface}/ifindex") as f:
                if f.read().strip() == iflink:
                    return iface
        except (OSError, IOError):
            continue

    raise RuntimeError(f"Could not find veth for container {container_id}")


class ExternalTcpDumpHandler(TcpDumpHandler):
    """TcpDump handler that runs tcpdump on the **host** veth interface.

    **Requires privilege:** The hermetic tcpdump binary must have ``CAP_NET_RAW``
    capability to capture on veth interfaces. This requires building with
    privilege and setting capabilities on the binary::

        sudo setcap cap_net_admin,cap_net_raw=eip bazel-bin/.../tcpdump

    **Requires --spawn_strategy=local:** Bazel's linux-sandbox strips file
    capabilities (xattrs) when copying files. Even with setcap or running as
    root, sandbox mode will fail the capability check.

    Use the ``tcpdump_external`` capability to check availability::

        @requires_capabilities("tcpdump_external")
        def test_external_traffic(target):
            with TcpDumpCapture(target.external_tcpdump_handler(), ...):
                ...

    Captures:
      - Traffic between the container and external networks
      - Container-to-container traffic (different containers)
      - Container-to-host traffic

    Does NOT capture:
      - Loopback traffic inside the container
      - Unix domain socket traffic
      - Shared memory IPC

    Uses the hermetic tcpdump binary (requires ``CAP_NET_RAW`` for veth capture).
    """

    def __init__(self, docker_target, tcpdump_bin: str):
        """Initialize the handler.

        :param docker_target: The :class:`DockerTarget` instance to capture from.
        :param tcpdump_bin: Path to the hermetic tcpdump binary.
        """
        self._target = docker_target
        self._tcpdump_bin = tcpdump_bin
        self._process_wrapper = None
        self._host_pcap_path = None

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
        """Start tcpdump on the host capturing the container's veth.

        The ``interface`` parameter is ignored — this handler always captures
        on the container's veth interface.

        :returns: The subprocess PID as a string.
        :rtype: str
        """
        # Find the container's veth interface on the host
        container_id = self._target.id
        veth = _get_container_veth(container_id)
        logger.info("Container %s veth interface: %s", container_id[:12], veth)

        # Store output path for retrieve()
        self._host_pcap_path = output_path

        # Build the command using the hermetic binary
        cmd = [
            "-i", veth,
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

        logger.info("Using hermetic tcpdump for host capture: %s", self._tcpdump_bin)
        self._process_wrapper = ProcessWrapper(
            binary_path=self._tcpdump_bin,
            args=cmd,
            logger_name="tcpdump-host",
        )
        self._process_wrapper.start_process()

        return str(self._process_wrapper.pid)

    def stop(self, handle):
        """Stop the tcpdump process.

        :param handle: The PID returned by :meth:`start`.
        """
        if self._process_wrapper:
            logger.info("Stopping tcpdump (PID %s)", handle)
            # Give tcpdump time to flush any buffered packets
            time.sleep(0.5)
            self._process_wrapper.kill_process()
            self._process_wrapper = None

    def retrieve(self, target_pcap_path, host_path):
        """Copy pcap from the temp location to the requested host path.

        :param target_pcap_path: Ignored for external handler.
        :param host_path: The host path where the pcap should be saved.
        """
        # External handler wrote to _host_pcap_path directly on host
        if self._host_pcap_path:
            if self._host_pcap_path != host_path:
                logger.debug("Copying pcap from %s to %s", self._host_pcap_path, host_path)
                shutil.copy2(self._host_pcap_path, host_path)
            else:
                logger.debug("Pcap already at %s", host_path)
        else:
            logger.warning("No pcap path recorded")
