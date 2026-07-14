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
"""ITF Logger Handler Plugin — structured file logging with section separators.

Redirects all Python logging output to a ``test.log`` file (configurable) using
the ITF log format::

    [2026-07-02 02:12:58.823] [DBG] [doip] Diagnostic message ACK received

Sections are emitted as visual separators for each lifecycle phase:

    ═══════════════════════════════════════════════════════════════════════════════
    ║ SESSION START
    ═══════════════════════════════════════════════════════════════════════════════

Usage in conftest::

    pytest_plugins = [
        "score.itf.core.itf_plugin",
        "score.itf.plugins.utility.logger.plugin",
    ]

CLI flags::

    --itf-logfile       Path to the log file (default: test.log)
    --itf-loglevel      Minimum log level (default: DEBUG)
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Format constants
# ---------------------------------------------------------------------------
_LEVEL_MAP = {
    logging.DEBUG: "DBG",
    logging.INFO: "INF",
    logging.WARNING: "WRN",
    logging.ERROR: "ERR",
    logging.CRITICAL: "CRT",
}

_SECTION_WIDTH = 79
_SECTION_CHAR = "═"
_SECTION_EDGE = "║"


# ---------------------------------------------------------------------------
# Formatter
# ---------------------------------------------------------------------------
class ItfLogFormatter(logging.Formatter):
    """Formats log records as: [timestamp] [LVL] [source] message

    Records with an ``_itf_section`` attribute are rendered as visual
    section separators instead of normal log lines.
    """

    def format(self, record: logging.LogRecord) -> str:
        section = getattr(record, "_itf_section", None)
        if section:
            return _section_block(section)
        ts = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        lvl = _LEVEL_MAP.get(record.levelno, "???")
        # Derive short source name from logger hierarchy
        name = record.name
        parts = name.split(".")
        # Use last meaningful segment (skip 'score.itf.plugins...' prefix noise)
        if len(parts) > 2 and parts[0] == "score":
            source = parts[-1] if parts[-1] != "plugin" else parts[-2]
        else:
            source = parts[-1] if parts else name
        msg = record.getMessage()
        return f"[{ts}] [{lvl}] [{source}] {msg}"


# ---------------------------------------------------------------------------
# Section helper
# ---------------------------------------------------------------------------
def _section_block(title: str) -> str:
    """Build a visual section separator."""
    bar = _SECTION_CHAR * _SECTION_WIDTH
    return f"\n{bar}\n{_SECTION_EDGE} {title}\n{bar}\n"


# ---------------------------------------------------------------------------
# Plugin
# ---------------------------------------------------------------------------
class ItfLoggerPlugin:
    """Captures all logging to a structured file with phase-based sections."""

    def __init__(self, logfile: Path, level: int) -> None:
        self._logfile = logfile
        self._level = level
        self._handler: logging.FileHandler | None = None
        self._session_start: float = 0.0

        # Install handler immediately at construction (during pytest_configure)
        self._handler = logging.FileHandler(self._logfile, mode="w", encoding="utf-8")
        self._handler.setLevel(self._level)
        self._handler.setFormatter(ItfLogFormatter())
        logging.root.addHandler(self._handler)
        logging.root.setLevel(min(logging.root.level, self._level))

    def _emit_section(self, title: str) -> None:
        """Write a section separator directly to the log file."""
        if self._handler:
            self._handler.stream.write(_section_block(title))
            self._handler.stream.flush()

    def _emit_line(self, msg: str) -> None:
        """Write a raw line to the log file (for graph dumps, etc.)."""
        if self._handler:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            self._handler.stream.write(f"[{ts}] [INF] [itf] {msg}\n")
            self._handler.stream.flush()

    # -- pytest hooks (session lifecycle) ----------------------------------

    @pytest.hookimpl(tryfirst=True)
    def pytest_sessionstart(self, session: pytest.Session) -> None:
        self._session_start = time.time()
        self._emit_section("SESSION START")
        self._emit_line(f"Log file: {self._logfile.resolve()}")
        self._emit_line(f"Log level: {logging.getLevelName(self._level)}")
        self._emit_line(f"Timestamp: {datetime.now().isoformat()}")

    @pytest.hookimpl(trylast=True)
    def pytest_sessionfinish(self, session: pytest.Session, exitstatus: int) -> None:
        elapsed = time.time() - self._session_start
        self._emit_section("SESSION FINISH")
        self._emit_line(f"Exit status: {exitstatus}")
        self._emit_line(f"Total duration: {elapsed:.3f}s")
        if self._handler:
            logging.root.removeHandler(self._handler)
            self._handler.close()
            self._handler = None

    # -- Test-level pytest hooks -------------------------------------------

    @pytest.hookimpl(tryfirst=True)
    def pytest_runtest_setup(self, item: pytest.Item) -> None:
        self._emit_section(f"TEST SETUP — {item.name}")
        self._emit_line(f"File: {item.fspath}")
        self._emit_line(f"NodeID: {item.nodeid}")

    @pytest.hookimpl(tryfirst=True)
    def pytest_runtest_call(self, item: pytest.Item) -> None:
        self._emit_section(f"TEST CALL — {item.name}")

    @pytest.hookimpl(tryfirst=True)
    def pytest_runtest_teardown(self, item: pytest.Item) -> None:
        self._emit_section(f"TEST TEARDOWN — {item.name}")

    @pytest.hookimpl(trylast=True)
    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        if report.when == "call":
            outcome = report.outcome.upper()
            duration = f"{report.duration:.3f}s"
            self._emit_line(f"Result: {outcome} ({duration})")


# ---------------------------------------------------------------------------
# Plugin registration
# ---------------------------------------------------------------------------
def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("itf-logger", "ITF structured file logger")
    group.addoption(
        "--itf-logfile",
        default="test.log",
        help="Path to ITF log output file (default: test.log)",
    )
    group.addoption(
        "--itf-loglevel",
        default="DEBUG",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Minimum log level for ITF log file (default: DEBUG)",
    )


def pytest_configure(config: pytest.Config) -> None:
    logfile = Path(config.getoption("--itf-logfile", default="test.log"))
    level_name = config.getoption("--itf-loglevel", default="DEBUG")
    level = getattr(logging, level_name, logging.DEBUG)
    plugin = ItfLoggerPlugin(logfile=logfile, level=level)
    config.pluginmanager.register(plugin, "itf-logger")
