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
"""Lifecycle plugin: compress collected test artifacts as gzip or zstd.

The plugin contributes only verbs (step handlers):

* ``ctf_collect`` captures each test report and enqueues compression work.
* background worker thread writes compressed records per test as they finish.
* ``ctf_session_teardown`` drains the queue and stops the worker cleanly.

Usage:
    pytest \
      --ctf-artifact-compression=gzip \
      --ctf-artifact-output-dir=.ctf-artifacts

    pytest \
      --ctf-artifact-compression=zstd \
      --ctf-artifact-output-dir=.ctf-artifacts

Notes:
* ``zstd`` requires the optional ``zstandard`` package.
* Compression is a lifecycle concern (WHEN plane): no provider is added.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import queue
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest


def pytest_addoption(parser):
    group = parser.getgroup("ctf-artifacts")
    group.addoption(
        "--ctf-artifact-compression",
        action="store",
        default="gzip",
        choices=["gzip", "zstd"],
        help="Compression algorithm for the CTF artifact bundle.",
    )
    group.addoption(
        "--ctf-artifact-output-dir",
        action="store",
        default=".ctf-artifacts",
        help="Directory where the compressed artifact bundle is written.",
    )


def pytest_configure(config):
    if config.getoption("--ctf-artifact-compression") != "zstd":
        return
    try:
        import zstandard  # noqa: F401
    except ModuleNotFoundError as exc:
        raise pytest.UsageError(
            "--ctf-artifact-compression=zstd requires package 'zstandard'."
        ) from exc

    _runtime(config)


def _json_safe(value: Any) -> Any:
    """Best-effort conversion so arbitrary artifact values stay serializable."""
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return repr(value)


def _record_path(output_dir: Path, algorithm: str, nodeid: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", nodeid).strip("._")
    safe = safe[:80] if safe else "test"
    digest = hashlib.sha1(nodeid.encode("utf-8")).hexdigest()[:10]
    ext = "json.gz" if algorithm == "gzip" else "json.zst"
    return output_dir / f"{safe}-{digest}.{ext}"


def _compress_zstd(raw: bytes) -> bytes:
    try:
        import zstandard as zstd  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:  # pragma: no cover - env-dependent
        raise RuntimeError(
            "--ctf-artifact-compression=zstd requires package 'zstandard'. "
            "Install it in the active venv."
        ) from exc

    return zstd.ZstdCompressor(level=3).compress(raw)


class _AsyncCompressor:
    def __init__(self, config) -> None:
        self._algorithm = config.getoption("--ctf-artifact-compression")
        self._out_dir = Path(config.getoption("--ctf-artifact-output-dir"))
        self._out_dir.mkdir(parents=True, exist_ok=True)
        self._jobs: queue.Queue[tuple[str, bytes] | None] = queue.Queue()
        self._error: Exception | None = None
        self._written = 0
        self._thread = threading.Thread(
            target=self._run,
            name="ctf-artifact-compressor",
            daemon=True,
        )
        self._thread.start()

    def submit(self, nodeid: str, raw: bytes) -> None:
        self._jobs.put((nodeid, raw))

    def close(self) -> dict[str, Any]:
        self._jobs.put(None)
        self._thread.join()
        if self._error is not None:
            raise RuntimeError("artifact compression worker failed") from self._error
        return {
            "algorithm": self._algorithm,
            "output_dir": str(self._out_dir),
            "files_written": self._written,
        }

    def _compress(self, raw: bytes) -> bytes:
        if self._algorithm == "gzip":
            return gzip.compress(raw, compresslevel=6)
        return _compress_zstd(raw)

    def _run(self) -> None:
        while True:
            job = self._jobs.get()
            if job is None:
                break
            nodeid, raw = job
            try:
                payload = self._compress(raw)
                path = _record_path(self._out_dir, self._algorithm, nodeid)
                path.write_bytes(payload)
                self._written += 1
            except Exception as exc:  # noqa: BLE001
                self._error = exc
                break


def _runtime(config) -> _AsyncCompressor:
    runtime = getattr(config, "_ctf_artifact_compressor", None)
    if runtime is None:
        runtime = _AsyncCompressor(config)
        setattr(config, "_ctf_artifact_compressor", runtime)
    return runtime


def collect_test_report(ctx):
    """Capture and asynchronously compress one record after each test call."""
    report = ctx.report
    item = ctx.item
    if report is None or item is None:
        return

    record = {
        "name": f"test-report:{item.nodeid}",
        "value": {
            "nodeid": item.nodeid,
            "outcome": report.outcome,
            "duration_s": getattr(report, "duration", None),
            "when": report.when,
        },
        "ts": datetime.now(timezone.utc).isoformat(),
    }

    ctx.artifacts.add(record["name"], record["value"])
    raw = (json.dumps(record, sort_keys=True) + "\n").encode("utf-8")
    _runtime(ctx.config).submit(item.nodeid, raw)


def compress_artifacts(ctx):
    """Drain the async queue and stop background compression."""
    summary = _runtime(ctx.config).close()
    ctx.artifacts.add("compression-summary", _json_safe(summary))
    setattr(ctx.config, "_ctf_artifact_bundle", summary["output_dir"])
    print(
        "[ctf-artifacts] finished async compression: "
        f"{summary['files_written']} files -> {summary['output_dir']} "
        f"({summary['algorithm']})"
    )


def pytest_ctf_steps(steps, config):
    steps.add("ctf_collect", collect_test_report)
    # Session teardown points execute in reverse order, so a low order makes
    # compression run late and include artifacts published by other teardown verbs.
    steps.add("ctf_session_teardown", compress_artifacts, order=-1000)
