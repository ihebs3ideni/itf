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
"""Bubblewrap-based execution environment.

This is the refactored version of the original ``score.sctf.sandbox.BwrapSandbox``,
implementing the unified :class:`Environment` interface so that SCTF tests can
transparently switch between Bubblewrap and Docker backends.
"""

import logging
import os
import shutil
import stat
import subprocess
import threading

import psutil
import tenacity

from score.itf.core.environment.base import Environment, ProcessHandle

logger = logging.getLogger(__name__)

LINE_BUFFER = ["/usr/bin/stdbuf", "-oL"]

# Default retry settings — importable from sctf.config when wired via plugin,
# but we keep sensible defaults here so the environment can be used standalone.
_RETRY_COUNT = 150
_RETRY_DELAY_S = 0.5
_TIMEOUT_S = 15


def _async_log(fd, logger_name: str) -> None:
    """Read lines from *fd* and emit them through a named logger."""
    log = logging.getLogger(logger_name)
    try:
        for line in fd:
            log.info(line.rstrip("\n"))
    except ValueError:
        pass  # fd closed


class BwrapEnvironment(Environment):
    """Run binaries inside a Bubblewrap namespace.

    Parameters:
        sysroot: Absolute path to the extracted root filesystem on the host.
        workspace: Path mapped as ``/tmp`` inside the sandbox.
        persistent: Path mapped as ``/persistent`` inside the sandbox.
        artifact_output_path: Path mapped as ``/tmp/artifacts``.
        bazel_solibs: A named-tuple ``(src, dst)`` for Bazel shared libs, or ``None``.
        extra_mount_list: List of ``(host, sandbox[, readonly])`` tuples for
            additional bind mounts.
        env_vars: Extra environment variables to inject (``--setenv``).
        run_under_tool: Optional tool prefix (e.g. ``"valgrind --tool=memcheck"``).
        run_under_app_list: App basenames that should be prefixed with *run_under_tool*.
        retry_count: Max retries when searching for the child PID.
        retry_delay: Seconds between retries.
        timeout: Default process stop timeout.
    """

    def __init__(
        self,
        *,
        sysroot: str,
        workspace: str = "/tmp",
        persistent: str | None = None,
        artifact_output_path: str | None = None,
        bazel_solibs=None,
        extra_mount_list: list | None = None,
        env_vars: dict[str, str] | None = None,
        run_under_tool: str = "",
        run_under_app_list: list[str] | None = None,
        retry_count: int = _RETRY_COUNT,
        retry_delay: float = _RETRY_DELAY_S,
        timeout: float = _TIMEOUT_S,
    ):
        self._sysroot = sysroot
        self._workspace = workspace
        self._persistent = persistent or f"{sysroot}/persistent"
        self._artifact_output_path = artifact_output_path
        self._bazel_solibs = bazel_solibs
        self._extra_mount_list = extra_mount_list or []
        self._env_vars = env_vars or {}
        self._run_under_tool = run_under_tool
        self._run_under_app_list = run_under_app_list or []
        self._retry_count = retry_count
        self._retry_delay = retry_delay
        self._timeout = timeout

        # Tracked handles for cleanup
        self._handles: list[ProcessHandle] = []

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def setup(self) -> None:
        """Bwrap needs no daemon — setup is a no-op."""

    def teardown(self) -> None:
        """Stop any processes still tracked by this environment."""
        for h in list(self._handles):
            try:
                if self.is_process_running(h):
                    self.stop_process(h)
            except Exception:  # noqa: BLE001
                logger.debug("Ignoring error during teardown of %s", h.pid, exc_info=True)
        self._handles.clear()

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def execute(self, path: str, args: list[str], cwd: str = "/") -> ProcessHandle:
        self._check_binary_path(path, cwd)

        bwrap_cmd = self._build_bwrap_cmd(cwd, self._extra_mount_list)
        if self._should_run_under(path):
            full_cmd = bwrap_cmd + LINE_BUFFER + self._run_under_tool.split() + [path] + args
        else:
            full_cmd = bwrap_cmd + LINE_BUFFER + [path] + args

        parent_proc = self._start_process(full_cmd)
        logger_name = os.path.basename(path)
        stdout_thread = self._start_logging_thread(parent_proc.stdout, logger_name)
        stderr_thread = self._start_logging_thread(parent_proc.stderr, logger_name)

        child_proc = None
        try:
            child_proc = self._find_application(parent_proc, path)
        except Exception:  # noqa: BLE001
            if not parent_proc.is_running():
                raise
            # Child may have finished before we could locate it — acceptable.

        handle = ProcessHandle(
            pid=child_proc.pid if child_proc else None,
            parent=parent_proc,
            child=child_proc,
            stdout_thread=stdout_thread,
            stderr_thread=stderr_thread,
        )
        self._handles.append(handle)
        return handle

    def stop_process(self, handle: ProcessHandle, timeout: float | None = None) -> int:
        timeout = timeout if timeout is not None else self._timeout

        if handle.child:
            exit_code = self._stop_child(handle, timeout)
        else:
            exit_code = self._stop_parent(handle, timeout)

        if handle.stdout_thread:
            handle.stdout_thread.join(timeout=5)
        if handle.stderr_thread:
            handle.stderr_thread.join(timeout=5)

        handle.exit_code = exit_code
        if handle in self._handles:
            self._handles.remove(handle)
        return exit_code

    def is_process_running(self, handle: ProcessHandle) -> bool:
        if handle.child:
            return handle.child.is_running()
        if handle.parent:
            return handle.parent.is_running()
        return False

    # ------------------------------------------------------------------
    # File transfer
    # ------------------------------------------------------------------

    def copy_to(self, host_path: str, env_path: str) -> None:
        sandbox_path = os.path.join(self._sysroot, env_path.lstrip("/"))
        os.makedirs(os.path.dirname(sandbox_path), exist_ok=True)
        if os.path.isdir(host_path):
            shutil.copytree(host_path, sandbox_path, dirs_exist_ok=True)
        else:
            shutil.copy2(host_path, sandbox_path)

    def copy_from(self, env_path: str, host_path: str) -> None:
        sandbox_path = os.path.join(self._sysroot, env_path.lstrip("/"))
        os.makedirs(os.path.dirname(host_path), exist_ok=True)
        if os.path.isdir(sandbox_path):
            shutil.copytree(sandbox_path, host_path, dirs_exist_ok=True)
        else:
            shutil.copy2(sandbox_path, host_path)

    # ------------------------------------------------------------------
    # Bwrap command construction (migrated from BwrapSandbox._bwrap_cmd)
    # ------------------------------------------------------------------

    def _build_bwrap_cmd(self, cwd: str, extra_mount_list: list | None = None) -> list[str]:
        cmd = [
            "/usr/bin/bwrap",
            "--die-with-parent",
            f"--bind {self._sysroot} /",
            f"--bind {self._workspace} /tmp",
            f"--bind {self._persistent} /persistent",
            "--ro-bind /bin /bin",
            "--ro-bind /lib /lib",
            "--ro-bind /lib64 /lib64",
            "--ro-bind /usr/lib /usr/lib",
            "--ro-bind /usr/bin /usr/bin",
        ]

        if self._artifact_output_path:
            cmd.append(f"--bind {self._artifact_output_path} /tmp/artifacts")

        cmd.extend([
            f"--chdir {cwd}",
            "--proc /proc",
            "--dev-bind /dev /dev",
            "--setenv TEST_PREMATURE_EXIT_FILE /tmp/gtest.exited_prematurely",
            "--setenv SCTF SCTF",
            "--setenv AMSR_DISABLE_INTEGRITY_CHECK 1",
        ])

        # Extra env vars
        for key, val in self._env_vars.items():
            cmd.append(f"--setenv {key} {val}")

        # Bazel shared libraries
        solibs_path = os.environ.get("SOLIBS_PATH")
        if solibs_path and self._bazel_solibs and self._bazel_solibs.src:
            cmd.append(f"--ro-bind {self._bazel_solibs.src} {self._bazel_solibs.dst}")
            cmd.append(f"--setenv LD_LIBRARY_PATH {solibs_path}")

        # Conditional host directory mounts
        for host_dir in ("/usr/lib64", "/usr/libexec"):
            if os.path.isdir(host_dir):
                cmd.append(f"--ro-bind {host_dir} {host_dir}")

        # Merge extra mounts
        all_extra = list(extra_mount_list or [])
        if self._extra_mount_list:
            all_extra.extend(self._extra_mount_list)

        for extra_data in all_extra:
            host_src = extra_data[0]
            sandbox_dst = extra_data[1]
            read_only = len(extra_data) >= 3 and isinstance(extra_data[2], bool) and extra_data[2]

            if isinstance(host_src, str) and os.path.isdir(host_src) and isinstance(sandbox_dst, str) and os.path.isabs(sandbox_dst):
                bind_type = "--ro-bind" if read_only else "--bind"
                cmd.append(f"{bind_type} {host_src} {sandbox_dst}")
            else:
                logger.warning("Skipping invalid extra mount: %s", extra_data)

        return " ".join(cmd).split()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _should_run_under(self, path: str) -> bool:
        if not self._run_under_tool:
            return False
        return any(app in path for app in self._run_under_app_list)

    def _check_binary_path(self, path: str, cwd: str) -> None:
        sandboxed = self._sysroot
        if os.path.isabs(cwd):
            sandboxed = sandboxed + cwd
        else:
            sandboxed = os.path.join(sandboxed, cwd)

        if os.path.isabs(path):
            sandboxed = sandboxed + path
        else:
            sandboxed = os.path.join(sandboxed, path)

        if not (os.path.isfile(sandboxed) and os.access(sandboxed, os.X_OK)):
            try:
                os.chmod(sandboxed, stat.S_IXOTH)
            except Exception as exc:
                raise RuntimeError(f"File is not a valid executable: {sandboxed}") from exc

    @staticmethod
    def _start_process(cmd: list[str]) -> psutil.Popen:
        try:
            return psutil.Popen(
                cmd,
                bufsize=0,
                universal_newlines=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                close_fds=True,
            )
        except Exception as exc:
            raise RuntimeError(f"Could not run {cmd}") from exc

    @staticmethod
    def _start_logging_thread(stream, logger_name: str) -> threading.Thread:
        t = threading.Thread(target=_async_log, args=(stream, logger_name), daemon=True)
        t.start()
        return t

    def _find_application(self, parent: psutil.Popen, target_path: str):
        @tenacity.retry(
            wait=tenacity.wait_fixed(self._retry_delay),
            stop=tenacity.stop_after_attempt(self._retry_count),
            reraise=True,
        )
        def _inner():
            def walk(proc):
                for child in proc.children():
                    if os.path.basename(child.exe()) == os.path.basename(target_path):
                        return child
                    if "valgrind" in child.cmdline() and target_path in child.cmdline():
                        return child
                    found = walk(child)
                    if found:
                        return found
                return None

            result = walk(parent)
            if result:
                return result
            if parent.poll() is not None:
                return None
            raise RuntimeError(f"Could not find target child process: {target_path}")

        return _inner()

    @staticmethod
    def _stop_child(handle: ProcessHandle, timeout: float) -> int:
        child = handle.child
        parent = handle.parent
        try:
            child.terminate()
            for _ in range(5):
                try:
                    child.wait(1)
                    break
                except psutil.TimeoutExpired:
                    pass
        except psutil.NoSuchProcess:
            logger.warning("Child already terminated")
        finally:
            if child.is_running():
                logger.error("Sending SIGKILL to child %s", child.pid)
                child.kill()
                child.wait()
        return parent.wait(timeout)

    @staticmethod
    def _stop_parent(handle: ProcessHandle, timeout: float) -> int:
        parent = handle.parent
        try:
            parent.terminate()
            return parent.wait(timeout)
        except psutil.TimeoutExpired:
            logger.error("Parent did not stop in %ss, sending SIGKILL", timeout)
            parent.kill()
            return parent.wait()
