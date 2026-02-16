# *******************************************************************************
# Copyright (c) 2025 Contributors to the Eclipse Foundation
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
"""SCTF component test — exercises multiple concurrent processes and IPC.

Uses standard Linux utilities as stand-ins for real software components to
validate the full SCTF lifecycle:

  - Multi-process orchestration (concurrent execute / stop_process)
  - Process exit-code propagation
  - File-based IPC between components running in the same container
  - Environment variable injection
  - Working-directory control
  - Copy-in configuration, copy-out results
"""

import logging
import pathlib
import time


# ---------------------------------------------------------------------------
# 1. Producer / Consumer via shared file
# ---------------------------------------------------------------------------

def test_producer_consumer_pipeline(docker_sandbox):
    """Two processes communicate through a shared file inside the container.

    *producer* writes numbered lines to ``/tmp/pipe.log`` using ``sh -c``.
    *consumer* waits for the file to appear, then tails and counts the lines.
    We verify that the consumer observes all lines written by the producer.
    """
    env = docker_sandbox.environment

    # Producer: write 10 lines to a shared file
    producer = env.execute("/bin/sh", [
        "-c",
        "for i in $(seq 1 10); do echo \"line $i\" >> /tmp/pipe.log; sleep 0.05; done",
    ])

    # Wait for the producer to finish naturally
    env.stop_process(producer, timeout=10)
    assert producer.exit_code == 0, f"producer failed with {producer.exit_code}"

    # Consumer: count lines in the shared file
    consumer = env.execute("/bin/sh", [
        "-c",
        "wc -l < /tmp/pipe.log",
    ])
    env.stop_process(consumer, timeout=5)
    assert consumer.exit_code == 0, f"consumer failed with {consumer.exit_code}"

    # Copy the file out and verify content
    workspace = pathlib.Path(docker_sandbox.tmp_workspace)
    dst = workspace / "pipe.log"
    env.copy_from("/tmp/pipe.log", str(dst))

    lines = dst.read_text().strip().splitlines()
    assert len(lines) == 10, f"expected 10 lines, got {len(lines)}"
    assert lines[0] == "line 1"
    assert lines[-1] == "line 10"


# ---------------------------------------------------------------------------
# 2. Environment variable injection
# ---------------------------------------------------------------------------

def test_env_vars_visible_to_process(docker_sandbox):
    """Verify that LD_LIBRARY_PATH (set by the environment) is visible."""
    env = docker_sandbox.environment

    handle = env.execute("/bin/sh", ["-c", "echo $LD_LIBRARY_PATH > /tmp/env_out.txt"])
    env.stop_process(handle, timeout=5)
    assert handle.exit_code == 0

    workspace = pathlib.Path(docker_sandbox.tmp_workspace)
    dst = workspace / "env_out.txt"
    env.copy_from("/tmp/env_out.txt", str(dst))

    value = dst.read_text().strip()
    assert "/usr/bazel/lib" in value, f"unexpected LD_LIBRARY_PATH: {value}"


# ---------------------------------------------------------------------------
# 3. Working directory control
# ---------------------------------------------------------------------------

def test_cwd_is_honoured(docker_sandbox):
    """Process should start in the requested working directory."""
    env = docker_sandbox.environment

    # Create a directory and a marker file
    h = env.execute("/bin/mkdir", ["-p", "/opt/myapp"])
    env.stop_process(h)
    h = env.execute("/bin/sh", ["-c", "echo marker > /opt/myapp/.config"])
    env.stop_process(h)

    # Run a process that reads a relative path — only works if cwd is correct
    handle = env.execute("/bin/cat", [".config"], cwd="/opt/myapp")
    env.stop_process(handle, timeout=5)
    assert handle.exit_code == 0, "cat .config should succeed when cwd=/opt/myapp"


# ---------------------------------------------------------------------------
# 4. Concurrent processes
# ---------------------------------------------------------------------------

def test_concurrent_processes(docker_sandbox):
    """Launch two processes simultaneously, verify both complete independently."""
    env = docker_sandbox.environment

    # Writer A: writes to /tmp/a.txt
    writer_a = env.execute("/bin/sh", [
        "-c", "sleep 0.2 && echo 'from_a' > /tmp/a.txt",
    ])

    # Writer B: writes to /tmp/b.txt
    writer_b = env.execute("/bin/sh", [
        "-c", "sleep 0.1 && echo 'from_b' > /tmp/b.txt",
    ])

    # Both should be running (or already finished) — no interference
    env.stop_process(writer_b, timeout=5)
    env.stop_process(writer_a, timeout=5)

    assert writer_a.exit_code == 0
    assert writer_b.exit_code == 0

    # Verify both files exist and have correct content
    workspace = pathlib.Path(docker_sandbox.tmp_workspace)

    env.copy_from("/tmp/a.txt", str(workspace / "a.txt"))
    env.copy_from("/tmp/b.txt", str(workspace / "b.txt"))

    assert (workspace / "a.txt").read_text().strip() == "from_a"
    assert (workspace / "b.txt").read_text().strip() == "from_b"


# ---------------------------------------------------------------------------
# 5. Copy-in config, run component, copy-out results
# ---------------------------------------------------------------------------

def test_config_driven_component(docker_sandbox):
    """Simulate a real workflow: deploy config, run a component, collect output.

    Uses ``awk`` as a stand-in data-processing component that reads an input
    CSV, applies a transformation (sums a column), and writes a result file.
    """
    env = docker_sandbox.environment
    workspace = pathlib.Path(docker_sandbox.tmp_workspace)

    # 1. Create input data locally
    input_csv = workspace / "data.csv"
    input_csv.write_text("item,value\nalpha,10\nbeta,20\ngamma,30\n")

    # 2. Deploy into the container
    h = env.execute("/bin/mkdir", ["-p", "/opt/data"])
    env.stop_process(h)
    env.copy_to(str(input_csv), "/opt/data/data.csv")

    # 3. Run the "component" — awk sums the value column
    handle = env.execute("/usr/bin/awk", [
        "-F,",
        "NR>1 { sum += $2 } END { print sum }",
        "/opt/data/data.csv",
    ], cwd="/opt/data")
    env.stop_process(handle, timeout=5)
    assert handle.exit_code == 0, f"awk failed with {handle.exit_code}"

    # 4. Run a second component that writes the result to a file
    handle2 = env.execute("/bin/sh", [
        "-c",
        "awk -F, 'NR>1 { sum += $2 } END { print sum }' /opt/data/data.csv > /opt/data/result.txt",
    ])
    env.stop_process(handle2, timeout=5)
    assert handle2.exit_code == 0

    # 5. Collect the output
    result_file = workspace / "result.txt"
    env.copy_from("/opt/data/result.txt", str(result_file))

    result = result_file.read_text().strip()
    assert result == "60", f"expected sum=60, got {result}"


# ---------------------------------------------------------------------------
# 6. Long-running daemon with forced stop
# ---------------------------------------------------------------------------

def test_stop_long_running_process(docker_sandbox):
    """Start a long-running process and stop it before it finishes naturally."""
    env = docker_sandbox.environment

    # Start a process that would run for 60 seconds
    daemon = env.execute("/bin/sleep", ["60"])

    # It should be running
    assert env.is_process_running(daemon), "sleep 60 should be running"

    # Force-stop with a short timeout
    exit_code = env.stop_process(daemon, timeout=1)

    # Give Docker a moment to propagate the kill
    time.sleep(0.5)

    # After stopping, it should no longer be running
    assert not env.is_process_running(daemon), "process should be stopped"
    # Exit code is non-zero because we killed it
    assert daemon.exit_code is not None


# ---------------------------------------------------------------------------
# 7. Noisy component with log capture + traffic trace
# ---------------------------------------------------------------------------

def test_noisy_component_log_capture(docker_sandbox, caplog):
    """Run a chatty component and verify its stdout/stderr are captured in the test log.

    Simulates a realistic application that logs lifecycle events to stdout and
    warnings/errors to stderr.  Uses pytest's ``caplog`` to assert that the
    ``_async_log`` background thread actually delivered the messages to
    Python's logging system.

    Also runs a client/server pair that exchanges data over a Unix socket and
    produces a hex-dump "trace" file — a lightweight stand-in for a pcap.
    """
    env = docker_sandbox.environment
    workspace = pathlib.Path(docker_sandbox.tmp_workspace)

    # -- Part A: chatty daemon with stdout + stderr --
    with caplog.at_level(logging.DEBUG):
        daemon = env.execute("/bin/sh", [
            "-c",
            # Simulate a component lifecycle: boot → heartbeats → shutdown
            "echo '[BOOT] Component v2.4.1 starting...';"
            "echo '[BOOT] Loading config from /etc/app/config.yaml';"
            "echo '[WARN] Key timeout not set, using default=5s' >&2;"
            "echo '[INFO] Binding to 0.0.0.0:8080';"
            "for i in $(seq 1 10); do"
            "  echo \"[HEARTBEAT] tick=$i status=ok mem=$(cat /proc/meminfo | head -1)\";"
            "  echo \"[TRACE] request_id=$i latency=${i}ms\" >&2;"
            "  sleep 0.02;"
            "done;"
            "echo '[INFO] Received SIGTERM, draining connections...';"
            "echo '[WARN] 2 pending connections dropped' >&2;"
            "echo '[INFO] Shutdown complete'",
        ])
        env.stop_process(daemon, timeout=15)
        assert daemon.exit_code == 0, f"daemon exited with {daemon.exit_code}"

    # Verify stdout lines were captured (INFO level in the "sh" logger)
    sh_records = [r for r in caplog.records if r.name == "sh"]
    stdout_messages = [r.message for r in sh_records if r.levelno == logging.INFO]
    stderr_messages = [r.message for r in sh_records if r.levelno == logging.WARNING]

    assert any("BOOT" in m for m in stdout_messages), (
        f"Expected BOOT message in stdout, got: {stdout_messages[:5]}"
    )
    assert any("HEARTBEAT" in m for m in stdout_messages), (
        f"Expected HEARTBEAT messages in stdout, got: {stdout_messages[:5]}"
    )
    assert any("Shutdown complete" in m for m in stdout_messages), (
        f"Expected shutdown message in stdout, got: {stdout_messages[-5:]}"
    )
    assert any("WARN" in m for m in stderr_messages), (
        f"Expected WARN messages in stderr, got: {stderr_messages[:5]}"
    )
    assert any("TRACE" in m for m in stderr_messages), (
        f"Expected TRACE messages in stderr, got: {stderr_messages[:5]}"
    )

    # -- Part B: client/server exchange with hex-dump trace --

    # A producer writes messages to a shared file while a "monitor" process
    # tails the file and produces a hex dump — simulating a traffic capture.
    h = env.execute("/bin/mkdir", ["-p", "/opt/trace"])
    env.stop_process(h)

    # Producer: write 5 "packets" to a log
    producer = env.execute("/bin/sh", [
        "-c",
        "for i in $(seq 1 5); do"
        "  echo \"PING seq=$i ts=$(date +%s%N)\" >> /opt/trace/raw.log;"
        "done",
    ])
    env.stop_process(producer, timeout=5)
    assert producer.exit_code == 0

    # Monitor: read the raw log, produce a hex dump (like a pcap)
    monitor = env.execute("/bin/sh", [
        "-c",
        "od -A x -t x1z /opt/trace/raw.log > /opt/trace/traffic.hex;"
        "echo \"[CAPTURE] $(wc -l < /opt/trace/traffic.hex) hex lines dumped\"",
    ])
    env.stop_process(monitor, timeout=5)
    assert monitor.exit_code == 0

    # Copy the hex-dump trace file out
    trace_file = workspace / "traffic.hex"
    env.copy_from("/opt/trace/traffic.hex", str(trace_file))

    trace_content = trace_file.read_text()
    assert len(trace_content) > 0, "Trace file should not be empty"
    # od output contains hex bytes — verify the payload is represented
    assert "PING" in trace_content or "50 49 4e 47" in trace_content, (
        f"Trace should contain 'PING' payload:\n{trace_content[:500]}"
    )
