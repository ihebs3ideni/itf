"""Real log capture plugin for structured logging."""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Any

from score.itf.framework import (
    plugin_contract,
    itf_hookimpl,
    OracleResult,
)

logger = logging.getLogger(__name__)


@dataclass
class LogCaptureState:
    """Log capture configuration and file handles.

    Owned by: log_capture plugin
    Stored in: context.use_state(LogCaptureState)
    """
    file_path: Path | None = None
    file_handle: Any = None
    log_formatter: Any = None
    stdout_redirect: Any = None
    stderr_redirect: Any = None
    handler: Any = None


class StructuredLineWriter:
    """Wraps a file stream to format writes as structured log lines."""

    def __init__(self, file_handle: Any):
        self.file_handle = file_handle
        self.buffer = ""

    def write(self, text: str) -> int:
        """Write with line-based formatting."""
        self.buffer += text
        lines = self.buffer.split("\n")

        # Write complete lines
        for line in lines[:-1]:
            self._write_structured(line)

        # Keep incomplete line in buffer
        self.buffer = lines[-1]
        return len(text)

    def _write_structured(self, line: str) -> None:
        """Write a structured log line."""
        if not line.strip():
            return

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        structured = f"[{timestamp}] [OUT] [capture] {line}\n"
        self.file_handle.write(structured)
        self.file_handle.flush()

    def flush(self) -> None:
        """Flush buffer."""
        if self.buffer.strip():
            self._write_structured(self.buffer)
            self.buffer = ""
        self.file_handle.flush()

    def isatty(self) -> bool:
        return False


class StructuredLogFormatter(logging.Formatter):
    """Custom formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as structured text."""
        timestamp = datetime.fromtimestamp(record.created).strftime(
            "%Y-%m-%d %H:%M:%S.%f"
        )[:-3]

        level_map = {
            logging.DEBUG: "DBG",
            logging.INFO: "INF",
            logging.WARNING: "WRN",
            logging.ERROR: "ERR",
            logging.CRITICAL: "CRT",
        }
        level = level_map.get(record.levelno, "???")

        source = record.name
        message = record.getMessage()

        return f"[{timestamp}] [{level}] [{source}] {message}"


@plugin_contract(
    name="score.itf.plugins.log_capture",
    provides=["log_capture"],
    description="Captures structured logs to a file",
)
class LogCapturePlugin:
    """Real log capture with structured output.

    Captures all application output and logging to a file with
    standardized format: [timestamp] [level] [source] message

    Lifecycle:
    1. Configure: determine log file path
    2. Start: open file, attach handlers, redirect stdout/stderr
    3. Stop: close file, restore streams
    """

    def pytest_addoption(self, parser):
        """Register pytest options."""
        parser.addoption(
            "--itf-log-capture-file",
            action="store",
            default=None,
            help="Path to file for structured log capture",
        )

    @itf_hookimpl
    def session_start_shared_resources_configure(self, context):
        """Configure log capture from pytest options."""
        logger.debug("LogCapturePlugin: configuring")

        if context.pytest_config is None:
            logger.debug("No pytest config available; skipping log capture config")
            return

        log_file = context.pytest_config.getoption(
            "itf_log_capture_file",
            default=None,
        )

        if log_file:
            path = Path(log_file)
            path.parent.mkdir(parents=True, exist_ok=True)

            state = context.use_state(
                LogCaptureState,
                owner="log_capture",
                factory=lambda: LogCaptureState(file_path=path),
            )
            state.file_path = path

            context.shared_resources["log_capture_file"] = str(path)
            logger.info(f"Log capture configured: {path}")

    @itf_hookimpl
    def session_start_logging_start(self, context):
        """Start log capture."""
        logger.info("LogCapturePlugin: starting capture")

        state = context.get_state(LogCaptureState)
        if state is None or state.file_path is None:
            logger.debug("Log capture not configured")
            return

        # Open log file
        file_handle = open(state.file_path, "w", encoding="utf-8")
        state.file_handle = file_handle

        # Attach logging handler
        formatter = StructuredLogFormatter()
        state.log_formatter = formatter

        handler = logging.StreamHandler(file_handle)
        handler.setFormatter(formatter)
        handler.setLevel(logging.DEBUG)

        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        state.handler = handler

        # Redirect stdout/stderr
        old_stdout = sys.stdout
        old_stderr = sys.stderr

        wrapped_stdout = StructuredLineWriter(file_handle)
        wrapped_stderr = StructuredLineWriter(file_handle)

        sys.stdout = wrapped_stdout
        sys.stderr = wrapped_stderr

        state.stdout_redirect = (old_stdout, wrapped_stdout)
        state.stderr_redirect = (old_stderr, wrapped_stderr)

        # Write header
        file_handle.write(f"=== ITF Session Log ===\n")
        file_handle.write(f"Started: {datetime.now()}\n")
        file_handle.write(f"Log file: {state.file_path}\n")
        file_handle.write(f"{'='*40}\n")
        file_handle.flush()

        logger.info(f"Logging started: {state.file_path}")

        # Register cleanup
        def cleanup_logging():
            try:
                if state.stdout_redirect:
                    state.stdout_redirect[1].flush()
                    sys.stdout = state.stdout_redirect[0]
                if state.stderr_redirect:
                    state.stderr_redirect[1].flush()
                    sys.stderr = state.stderr_redirect[0]
                if state.handler:
                    root_logger.removeHandler(state.handler)
                    state.handler.close()
                if state.file_handle:
                    state.file_handle.close()
            except Exception as exc:
                print(f"Error cleaning up logging: {exc}")

        context.add_cleanup_callback(cleanup_logging)

    @itf_hookimpl
    def session_finish_logging_stop(self, context):
        """Stop logging (explicit phase; cleanup callback handles actual cleanup)."""
        logger.info("LogCapturePlugin: stopping capture")

        state = context.get_state(LogCaptureState)
        if state and state.file_handle:
            state.file_handle.write(f"\nFinished: {datetime.now()}\n")
            state.file_handle.flush()

    @itf_hookimpl
    def session_start_readiness_check(self, context):
        """Check log capture is ready."""
        logger.debug("LogCapturePlugin: readiness check")

        state = context.get_state(LogCaptureState)
        if state is None or state.file_path is None:
            return OracleResult.skip_check(
                name="log_capture_ready",
                details="Log capture not configured",
            )

        if state.file_handle is None:
            return OracleResult.fail_check(
                name="log_capture_ready",
                details="Log file not opened",
                blocking=True,
            )

        return OracleResult.pass_check(
            name="log_capture_ready",
            details=f"Logging to {state.file_path}",
        )

    @itf_hookimpl
    def pytest_runtest_logstart(self, nodeid, location):
        """Log when test starts."""
        _ = location
        context = getattr(self, "_itf_context", None)
        state = context.get_state(LogCaptureState) if context is not None else None
        if state and state.file_handle:
            state.file_handle.write(
                f"\n[TEST START] {nodeid}\n"
            )
            state.file_handle.flush()

    @itf_hookimpl
    def pytest_runtest_logreport(self, report):
        """Log test result."""
        context = getattr(self, "_itf_context", None)
        if report.when == "call":
            state = context.get_state(LogCaptureState) if context is not None else None
            if state and state.file_handle:
                outcome = "PASSED" if report.outcome == "passed" else "FAILED"
                state.file_handle.write(
                    f"[TEST {outcome}] {report.nodeid}\n"
                )
                state.file_handle.flush()
