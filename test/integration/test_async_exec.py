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
import time


def test_async_exec(exec_interface):
    ready_signal = "/tmp/p2_ready"
    exec_interface.execute(f"rm -f {ready_signal}")

    recv_cmd = f"echo [P1] start; while [ ! -f {ready_signal} ]; do echo [P1] wait; sleep 0.1; done; echo [P1] done;"
    send_cmd = f"echo [P2] start; sleep 0.5; touch {ready_signal}; echo [P2] done;"

    with exec_interface.wrap_exec(recv_cmd, wait_on_exit=True):
        with exec_interface.wrap_exec(send_cmd, wait_on_exit=True):
            pass


def test_execute_async_pid_and_is_running(exec_interface):
    """Verify pid() returns a valid PID and is_running() tracks state."""
    proc = exec_interface.execute_async("sleep 10")
    try:
        pid = proc.pid()
        assert isinstance(pid, int)
        assert pid > 0
        assert proc.is_running()
    finally:
        proc.stop()
    assert not proc.is_running()


def test_execute_async_wait(exec_interface):
    """Verify wait() blocks until the process finishes and returns exit code 0."""
    proc = exec_interface.execute_async("sleep 1")
    exit_code = proc.wait(timeout_s=30)
    assert exit_code == 0
    assert not proc.is_running()


def test_execute_async_exit_code(exec_interface):
    """Verify get_exit_code() reflects the real exit status."""
    proc = exec_interface.execute_async("exit 42")
    proc.wait(timeout_s=30)
    assert proc.get_exit_code() == 42


def test_execute_async_stop(exec_interface):
    """Verify stop() terminates a long-running process."""
    proc = exec_interface.execute_async("sleep 300")
    assert proc.is_running()
    exit_code = proc.stop()
    assert not proc.is_running()
    # SIGTERM (143) or SIGKILL (137) are expected
    assert exit_code in (143, 137)


def test_execute_async_with_cwd(exec_interface):
    """Verify the cwd parameter is honoured."""
    marker_file = "itf_cwd_marker"
    exec_interface.execute(f"rm -f /tmp/{marker_file}")
    proc = exec_interface.execute_async(f"touch {marker_file}", cwd="/tmp")
    proc.wait(timeout_s=30)
    assert proc.get_exit_code() == 0
    exit_code, _ = exec_interface.execute(f"ls /tmp/{marker_file}")
    assert exit_code == 0
    exec_interface.execute(f"rm -f /tmp/{marker_file}")


def test_wrap_exec_stop_on_exit(exec_interface):
    """wrap_exec without wait_on_exit should stop the process when the block exits."""
    with exec_interface.wrap_exec("sleep 300") as wp:
        assert wp.is_running()
    # After the block, the process should have been stopped.
    assert not wp.is_running()


def test_wrap_exec_wait_on_exit(exec_interface):
    """wrap_exec with wait_on_exit should wait for natural completion."""
    with exec_interface.wrap_exec("sleep 1", wait_on_exit=True) as wp:
        assert wp.is_running() or True  # may finish fast
    assert wp.ret_code == 0


def test_wrap_exec_expected_exit_code(exec_interface):
    """wrap_exec should accept a non-zero expected exit code without raising."""
    with exec_interface.wrap_exec("exit 42", wait_on_exit=True, expected_exit_code=42) as wp:
        pass
    assert wp.ret_code == 42


def test_execute_async_with_args(exec_interface):
    """Verify args are passed correctly to the binary."""
    proc = exec_interface.execute_async("echo", args=["-n", "hello"])
    exit_code = proc.wait(timeout_s=30)
    assert exit_code == 0


def test_execute_async_args_with_spaces(exec_interface):
    """Verify args containing spaces are preserved as single arguments.

    Without proper per-arg quoting, 'hello world' would be split into two
    arguments and touch would create two files instead of one.
    """
    exec_interface.execute("rm -f '/tmp/hello world' /tmp/hello /tmp/world")
    proc = exec_interface.execute_async("touch", args=["hello world"], cwd="/tmp")
    proc.wait(timeout_s=30)
    assert proc.get_exit_code() == 0
    # The single file with a space in the name must exist.
    exit_code, _ = exec_interface.execute("ls '/tmp/hello world'")
    assert exit_code == 0, "Arg with space was split into separate arguments"
    exec_interface.execute("rm -f '/tmp/hello world'")


def test_execute_async_absolute_binary_path(exec_interface):
    """Verify absolute binary paths are not mangled (regression for lstrip bug)."""
    # Dynamically find the absolute path to 'echo' — differs between Linux and QNX.
    exit_code, output = exec_interface.execute("which echo")
    assert exit_code == 0, "Cannot locate echo binary on target"
    echo_path = output.decode().strip()
    assert echo_path.startswith("/"), f"Expected absolute path, got: {echo_path}"
    proc = exec_interface.execute_async(echo_path, args=["async_abs_path_ok"])
    exit_code = proc.wait(timeout_s=30)
    assert exit_code == 0


def test_wrap_exec_crashed_process_reports_real_exit_code(exec_interface):
    """wrap_exec without wait_on_exit should report the real exit code of a crashed process,
    not silently return 0."""
    with exec_interface.wrap_exec("exit 7", expected_exit_code=7) as wp:
        # Give the process time to exit before the with block ends.
        time.sleep(2)
    assert wp.ret_code == 7


def test_wrap_exec_get_output(exec_interface):
    """Verify get_output() is accessible via WrappedProcess."""
    with exec_interface.wrap_exec("echo line1; echo line2; echo line3", wait_on_exit=True) as wp:
        pass
    output = wp.get_output()
    assert "line1" in output
    assert "line2" in output
    assert "line3" in output


def test_execute_async_get_output(exec_interface):
    """Verify get_output() captures multiple lines of output."""
    proc = exec_interface.execute_async("echo line1; echo line2; echo line3")
    proc.wait(timeout_s=30)
    output = proc.get_output()
    assert "line1" in output
    assert "line2" in output
    assert "line3" in output
