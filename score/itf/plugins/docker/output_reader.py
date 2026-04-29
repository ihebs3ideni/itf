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
"""Background output reader for detached Docker exec processes.

:class:`OutputReader` drains a Docker exec output stream in a daemon thread,
forwarding each line to the Python logging system so that it appears in
pytest's live-log / captured output.
"""

import logging
import threading

logger = logging.getLogger(__name__)


class OutputReader:
    """Drains a Docker exec output stream in a background daemon thread.

    Each line of stdout/stderr is forwarded to the Python ``logging`` system so
    that it appears in pytest's ``live log`` / captured output.
    """

    def __init__(self, exec_id, output_generator, cmd_label=None):
        """Initialize the output reader.

        :param exec_id: The Docker exec ID (will be truncated to 12 chars).
        :param output_generator: Generator yielding (stdout, stderr) chunks.
        :param cmd_label: Optional label for log messages (defaults to exec_id).
        """
        self._exec_id = exec_id[:12]
        self._label = cmd_label or self._exec_id
        self._gen = output_generator
        self._lines: list[str] = []
        self._thread = threading.Thread(
            target=self._drain, name=f"exec-log-{self._exec_id}", daemon=True
        )
        self._thread.start()

    def _drain(self):
        try:
            for stdout_chunk, stderr_chunk in self._gen:
                for chunk, stream_name in ((stdout_chunk, "stdout"), (stderr_chunk, "stderr")):
                    if not chunk:
                        continue
                    for line in chunk.decode("utf-8", errors="replace").splitlines():
                        self._lines.append(line)
                        logger.info("[%s] %s", self._label, line)
        except Exception:
            logger.debug("Output reader for %s stopped", self._exec_id, exc_info=True)

    def join(self, timeout=2.0):
        """Wait for the reader thread to finish (call after exec exits).

        :param timeout: Maximum seconds to wait for the thread.
        """
        self._thread.join(timeout=timeout)

    @property
    def output(self):
        """All captured lines so far."""
        return list(self._lines)
