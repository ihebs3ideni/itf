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
starts packet capture on a target and retrieves the ``.pcap`` to the host.

The actual mechanism for running capture is delegated to a
:class:`TcpDumpHandler` — an abstract interface that each target plugin
implements. The handler is responsible for:

- Building the capture command (which binary, which flags)
- Starting/stopping the capture process
- Retrieving the pcap file

This keeps the capture logic generic while allowing Docker, QEMU, or hardware
targets to each provide their own strategy (e.g., different capture tools).

Example::

    from score.itf.core.com.tcpdump import TcpDumpCapture

    # Capture inside container/target:
    with TcpDumpCapture(target.internal_tcpdump_handler(), filter_expr="port 53") as cap:
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
    """Strategy interface for starting/stopping packet capture on a target.

    Target plugins subclass this and implement all three methods.
    The handler is responsible for:

    - Building the capture command (which binary, which flags)
    - Starting the capture process
    - Stopping the capture
    - Retrieving the pcap file to the host

    This allows each target to use different capture tools or flag formats.
    """

    @abc.abstractmethod
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
        """Start packet capture with the given parameters.

        The handler builds the appropriate command for its target.

        :param output_path: Path where the pcap should be written (on target).
        :param interface: Network interface to capture on.
        :param filter_expr: Optional BPF filter expression.
        :param snapshot_length: Max bytes per packet (0 = unlimited).
        :param max_packets: Stop after N packets (None = unlimited).
        :param extra_args: Additional CLI flags (handler-specific).
        :returns: An opaque handle for :meth:`stop` and :meth:`retrieve`.
        :rtype: str
        """

    @abc.abstractmethod
    def stop(self, handle: str) -> None:
        """Stop the capture process identified by *handle*.

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
    """Run packet capture on any ITF target and copy the pcap on exit.

    Attributes:
        handle: The opaque handle returned by the handler's ``start()``
            (populated after ``__enter__``).
        host_path: Path on the host where the pcap will be saved.
        target_path: Path on the target where the capture writes.
    """

    def __init__(
        self,
        handler: TcpDumpHandler,
        host_output_path=None,
        *,
        interface="any",
        filter_expr="",
        target_pcap_path="/tmp/capture.pcap",
        snapshot_length=0,
        max_packets=None,
        extra_args=None,
    ):
        """Initialise a capture session (does **not** start capture yet).

        :param handler: A :class:`TcpDumpHandler` that knows how to run capture
            on the specific target type.
        :param host_output_path: Where to save the pcap on the host. If ``None``
            a temporary file is created automatically.
        :param interface: Network interface to capture on (default ``"any"``).
        :param filter_expr: Optional BPF filter expression (e.g. ``"port 80"``).
        :param target_pcap_path: Path on the target for the pcap file.
        :param snapshot_length: Max bytes per packet (0 = unlimited).
        :param max_packets: Stop after N packets (None = unlimited).
        :param extra_args: Additional CLI flags passed to the capture tool.
        """
        self._handler = handler
        self._host_output_path = host_output_path
        self._interface = interface
        self._filter_expr = filter_expr
        self._target_pcap_path = target_pcap_path
        self._snapshot_length = snapshot_length
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
        """Target-side path where capture writes."""
        return self._target_pcap_path

    # -- context manager protocol --------------------------------------------

    def __enter__(self):
        """Start capture via the handler."""
        # Resolve host output path
        if self._host_output_path is None:
            tmp = tempfile.NamedTemporaryFile(
                suffix=".pcap", prefix="itf_capture_", delete=False,
            )
            self._host_output_path = tmp.name
            tmp.close()
            self._tmpfile_created = True

        # Delegate to handler — it builds the command for its target
        self._handle = self._handler.start(
            output_path=self._target_pcap_path,
            interface=self._interface,
            filter_expr=self._filter_expr,
            snapshot_length=self._snapshot_length,
            max_packets=self._max_packets,
            extra_args=self._extra_args,
        )

        # Give capture a moment to start
        time.sleep(0.5)

        logger.info(
            "Capture started on interface '%s' → %s",
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
