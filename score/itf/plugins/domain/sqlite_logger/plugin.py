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
"""ITF SQLite Logger — persist test results, logs, and artifacts to a local DB.

Usage in conftest::

    pytest_plugins = [
        "score.itf.core.itf_plugin",
        "score.itf.plugins.domain.sqlite_logger.plugin",
    ]

CLI flags::

    --itf-sqlite             Enable SQLite logging (default: off)
    --itf-sqlite-path        Path to DB file (default: itf_results.db)

This is a domain plugin — it doesn't contribute capabilities to the DUT graph.
It records framework events, test outcomes, and artifacts for offline analysis.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any

import pytest

from score.itf.core.ctf.dut import DUT

logger = logging.getLogger(__name__)

_DB_ATTR = "_itf_sqlite_db"


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
_SCHEMA = """\
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at REAL NOT NULL,
    finished_at REAL,
    exit_status INTEGER,
    composition_json TEXT
);

CREATE TABLE IF NOT EXISTS lifecycle_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id),
    phase TEXT NOT NULL,
    timestamp REAL NOT NULL,
    detail_json TEXT
);

CREATE TABLE IF NOT EXISTS test_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id),
    nodeid TEXT NOT NULL,
    outcome TEXT NOT NULL,
    duration REAL,
    when_phase TEXT,
    timestamp REAL NOT NULL,
    longrepr TEXT,
    stdout TEXT,
    stderr TEXT
);

CREATE TABLE IF NOT EXISTS artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id),
    test_nodeid TEXT,
    name TEXT NOT NULL,
    content_type TEXT DEFAULT 'application/octet-stream',
    data BLOB,
    timestamp REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_test_results_session ON test_results(session_id);
CREATE INDEX IF NOT EXISTS idx_test_results_outcome ON test_results(outcome);
CREATE INDEX IF NOT EXISTS idx_artifacts_session ON artifacts(session_id);
"""


# ---------------------------------------------------------------------------
# DB connection management
# ---------------------------------------------------------------------------
class ITFDatabase:
    """Thin wrapper around a session-scoped SQLite connection."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._conn: sqlite3.Connection | None = None
        self._session_id: int | None = None

    @property
    def session_id(self) -> int:
        assert self._session_id is not None
        return self._session_id

    def open(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        cur = self._conn.execute("INSERT INTO sessions (started_at) VALUES (?)", (time.time(),))
        self._session_id = cur.lastrowid
        self._conn.commit()

    def close(self, exit_status: int | None = None) -> None:
        if self._conn is None:
            return
        self._conn.execute(
            "UPDATE sessions SET finished_at = ?, exit_status = ? WHERE id = ?",
            (time.time(), exit_status, self._session_id),
        )
        self._conn.commit()
        self._conn.close()
        self._conn = None

    def log_lifecycle(self, phase: str, detail: dict[str, Any] | None = None) -> None:
        if self._conn is None:
            return
        self._conn.execute(
            "INSERT INTO lifecycle_events (session_id, phase, timestamp, detail_json) VALUES (?, ?, ?, ?)",
            (self._session_id, phase, time.time(), json.dumps(detail) if detail else None),
        )
        self._conn.commit()

    def log_test(
        self,
        nodeid: str,
        outcome: str,
        duration: float | None,
        when: str,
        longrepr: str | None = None,
        stdout: str | None = None,
        stderr: str | None = None,
    ) -> None:
        if self._conn is None:
            return
        self._conn.execute(
            "INSERT INTO test_results "
            "(session_id, nodeid, outcome, duration, when_phase, timestamp, longrepr, stdout, stderr) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (self._session_id, nodeid, outcome, duration, when, time.time(), longrepr, stdout, stderr),
        )
        self._conn.commit()

    def store_artifact(
        self,
        name: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        test_nodeid: str | None = None,
    ) -> None:
        if self._conn is None:
            return
        self._conn.execute(
            "INSERT INTO artifacts (session_id, test_nodeid, name, content_type, data, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (self._session_id, test_nodeid, name, content_type, data, time.time()),
        )
        self._conn.commit()

    def store_composition(self, composition: dict[str, Any]) -> None:
        if self._conn is None:
            return
        self._conn.execute(
            "UPDATE sessions SET composition_json = ? WHERE id = ?",
            (json.dumps(composition), self._session_id),
        )
        self._conn.commit()


# ---------------------------------------------------------------------------
# Pytest hooks
# ---------------------------------------------------------------------------
def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("itf-sqlite", "ITF SQLite Logger")
    group.addoption(
        "--itf-sqlite",
        action="store_true",
        default=False,
        help="Enable SQLite result logging.",
    )
    group.addoption(
        "--itf-sqlite-path",
        type=str,
        default="itf_results.db",
        help="Path to the SQLite database file (default: itf_results.db).",
    )


def _get_db(config: pytest.Config) -> ITFDatabase | None:
    return getattr(config, _DB_ATTR, None)


_config_ref: pytest.Config | None = None


@pytest.hookimpl
def pytest_itf_declare(registry, config):
    global _config_ref  # noqa: PLW0603
    if not config.getoption("--itf-sqlite", default=False):
        return
    _config_ref = config
    db_path = Path(config.getoption("--itf-sqlite-path"))
    db = ITFDatabase(db_path)
    db.open()
    setattr(config, _DB_ATTR, db)
    db.log_lifecycle("declare")


@pytest.hookimpl
def pytest_itf_init(dut: DUT, config: pytest.Config) -> None:
    db = _get_db(config)
    if db is None:
        return
    db.log_lifecycle("init")


@pytest.hookimpl
def pytest_itf_provision(dut: DUT, config: pytest.Config) -> None:
    db = _get_db(config)
    if db:
        db.log_lifecycle("provision")


@pytest.hookimpl
def pytest_itf_verify(dut: DUT, config: pytest.Config) -> None:
    db = _get_db(config)
    if db:
        db.log_lifecycle("verify")
        # Store composition snapshot (DUT is fully resolved at this point)
        db.store_composition(
            {
                "contracts": sorted(dut.provides()),
                "spine": sorted(dut._assembly.plan.spine),
                "unavailable": dut._assembly.plan.unavailable,
                "tier_map": dut._assembly.plan.tier_of,
                "disabled": sorted(dut.disabled),
            }
        )


def pytest_runtest_logreport(report):
    if _config_ref is None:
        return
    db = _get_db(_config_ref)
    if db is None:
        return
    longrepr = str(report.longrepr) if report.longrepr else None
    stdout = report.capstdout if hasattr(report, "capstdout") else None
    stderr = report.capstderr if hasattr(report, "capstderr") else None
    db.log_test(
        nodeid=report.nodeid,
        outcome=report.outcome,
        duration=report.duration,
        when=report.when,
        longrepr=longrepr,
        stdout=stdout,
        stderr=stderr,
    )


@pytest.hookimpl
def pytest_itf_teardown(dut: DUT, config: pytest.Config) -> None:
    db = _get_db(config)
    if db:
        db.log_lifecycle("teardown")


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    db = _get_db(session.config)
    if db:
        db.close(exit_status=exitstatus)


# ---------------------------------------------------------------------------
# Fixture: expose DB for artifact storage in tests
# ---------------------------------------------------------------------------
@pytest.fixture
def itf_db(request: pytest.FixtureRequest) -> ITFDatabase | None:
    """Access the ITF SQLite database for storing test artifacts.

    Returns None if --itf-sqlite is not enabled.

    Example::

        def test_something(itf_db, exec_interface):
            result = exec_interface.execute("dmesg")
            if itf_db:
                itf_db.store_artifact("dmesg.txt", result.encode(),
                                      content_type="text/plain",
                                      test_nodeid=request.node.nodeid)
    """
    return _get_db(request.config)
