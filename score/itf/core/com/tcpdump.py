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
"""Packet capture support for ITF targets.

Provides :class:`TcpDumpCapture` — a target-agnostic context manager that
starts ``tcpdump`` on a target, captures traffic into a ``.pcap`` file, and
retrieves it to the host on exit.

The actual mechanism for running and stopping tcpdump is delegated to a
:class:`TcpDumpHandler` — an abstract interface that each target plugin
implements.  This keeps the capture logic in ``core/com`` while allowing
Docker, QEMU, or hardware targets to each provide their own strategy.

Example::

    from score.itf.core.com.tcpdump import TcpDumpCapture

    # ``target.tcpdump_handler()`` is provided by each target plugin
    with TcpDumpCapture(target.tcpdump_handler(), filter_expr="port 53") as cap:
        target.exec(["curl", "http://example.com"], detach=False)
    # cap.host_path now points to the pcap on the host
"""

import abc
import logging
import os
import tempfile
import time

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Abstract handler — each target plugin provides an implementation
# ---------------------------------------------------------------------------

class TcpDumpHandler(abc.ABC):
    """Strategy interface for starting/stopping tcpdump on a target.

    Target plugins must subclass this and implement all three methods.
    """

    @abc.abstractmethod
    def start(self, cmd: list[str]) -> str:
        """Start tcpdump with *cmd* on the target.

        :param cmd: The full tcpdump command line (list of strings).
            The capture path is already embedded via ``-w``.
        :returns: An opaque handle (e.g. exec-ID, PID, SSH channel) that
            :meth:`stop` and :meth:`retrieve` can use later.
        :rtype: str
        """

    @abc.abstractmethod
    def stop(self, handle: str) -> None:
        """Stop the tcpdump process identified by *handle*.

        :param handle: The opaque handle returned by :meth:`start`.
        """

    @abc.abstractmethod
    def retrieve(self, target_pcap_path: str, host_path: str) -> None:
        """Copy the pcap file from the target to *host_path*.

        :param target_pcap_path: Path to the pcap file on the target.
        :param host_path: Destination path on the host.
        """


# ---------------------------------------------------------------------------
# TcpDumpCapture — the public context manager
# ---------------------------------------------------------------------------

class TcpDumpCapture:
    """Run ``tcpdump`` on any ITF target and copy the pcap on exit.

    Attributes:
        handle: The opaque handle returned by the handler's ``start()``
            (populated after ``__enter__``).
        host_path: Path on the host where the pcap will be saved.
        target_path: Path on the target where tcpdump writes.
    """

    def __init__(
        self,
        handler: TcpDumpHandler,
        host_output_path=None,
        *,
        interface="any",
        filter_expr="",
        target_pcap_path="/tmp/capture.pcap",
        tcpdump_binary="/usr/sbin/tcpdump",
        snapshot_length=0,
        rotate_seconds=None,
        max_packets=None,
        extra_args=None,
    ):
        """Initialise a capture session (does **not** start tcpdump yet).

        :param handler: A :class:`TcpDumpHandler` that knows how to run tcpdump
            on the specific target type.
        :param host_output_path: Where to save the pcap on the host.  If ``None``
            a temporary file is created automatically.
        :param interface: Network interface to capture on (default ``"any"``).
        :param filter_expr: Optional BPF filter expression (e.g. ``"port 80"``).
        :param target_pcap_path: Path on the target for the pcap file.
        :param tcpdump_binary: Path to tcpdump on the target.
        :param snapshot_length: ``-s`` flag — max bytes per packet (0 = unlimited).
        :param rotate_seconds: If set, ``-G <seconds>`` to rotate capture files.
        :param max_packets: If set, ``-c <count>`` to stop after N packets.
        :param extra_args: Additional CLI flags passed verbatim to tcpdump.
        """
        self._handler = handler
        self._host_output_path = host_output_path
        self._interface = interface
        self._filter_expr = filter_expr
        self._target_pcap_path = target_pcap_path
        self._tcpdump_binary = tcpdump_binary
        self._snapshot_length = snapshot_length
        self._rotate_seconds = rotate_seconds
        self._max_packets = max_packets
        self._extra_args = extra_args

        self._handle = None
        self._tmpfile_created = False

    # -- public properties ---------------------------------------------------

    @property
    def handle(self):
        """Opaque handle for the running tcpdump process."""
        return self._handle

    @property
    def host_path(self):
        """Host-side path where the pcap will be (or has been) saved."""
        return self._host_output_path

    @property
    def target_path(self):
        """Target-side path where tcpdump writes."""
        return self._target_pcap_path

    # -- context manager protocol --------------------------------------------

    def __enter__(self):
        """Build the command line, start tcpdump via the handler."""
        cmd = [
            self._tcpdump_binary,
            "-i", self._interface,
            "-w", self._target_pcap_path,
            "-U",  # packet-buffered output
        ]
        if self._snapshot_length:
            cmd += ["-s", str(self._snapshot_length)]
        if self._rotate_seconds:
            cmd += ["-G", str(self._rotate_seconds)]
        if self._max_packets:
            cmd += ["-c", str(self._max_packets)]
        if self._extra_args:
            cmd.extend(self._extra_args)
        if self._filter_expr:
            cmd.extend(self._filter_expr.split())

        # Resolve host output path
        if self._host_output_path is None:
            tmp = tempfile.NamedTemporaryFile(
                suffix=".pcap", prefix="itf_tcpdump_", delete=False,
            )
            self._host_output_path = tmp.name
            tmp.close()
            self._tmpfile_created = True

        self._handle = self._handler.start(cmd)
        # Give tcpdump a moment to open the interface
        time.sleep(0.5)

        logger.info(
            "tcpdump started on interface '%s' → %s",
            self._interface,
            self._target_pcap_path,
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Stop tcpdump, retrieve the pcap to the host."""
        self._handler.stop(self._handle)

        try:
            self._handler.retrieve(
                self._target_pcap_path, self._host_output_path,
            )
            logger.info(
                "Pcap saved to %s (%d bytes)",
                self._host_output_path,
                os.path.getsize(self._host_output_path),
            )
        except Exception:
            logger.warning("Failed to retrieve pcap from target", exc_info=True)

    # -- helpers -------------------------------------------------------------

    def __repr__(self):
        return (
            f"TcpDumpCapture(handle={self._handle!r}, "
            f"host_path={self._host_output_path!r})"
        )
