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
"""Responsible for handling process lifetime."""

import os
import stat
import subprocess
import threading
import logging
import psutil
import tenacity
import score.sctf.config as sctf_config
from score.sctf.utils import is_file_executable
from score.sctf.exception import SctfRuntimeError, SctfAssertionError
from score.sctf.sandbox import async_log

logger = logging.getLogger(__name__)
LINE_BUFFER = ["/usr/bin/stdbuf", "-oL"]


class BaseEnvironment:
    """Simple class providing common environment execution utilities, i.e. logging thread startup."""

    def __init__(self, environment, extra_mount_list=None):
        self.environment = environment
        self.extra_mount_list = extra_mount_list

    def start(self, path, args, cwd):
        pass

    def start_internal(self, path, args, sandbox_cmd, logger_name):
        process = self._start_process(sandbox_cmd + [path] + args)
        stdout_thread, stderr_thread = self._start_loggers(process.stdout, process.stderr, logger_name)
        return process, stdout_thread, stderr_thread

    @staticmethod
    def _start_process(cmd):
        """Uses popen to start a process"""
        try:
            return psutil.Popen(
                cmd, bufsize=0, universal_newlines=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True
            )
        except Exception as ex:
            raise SctfAssertionError(f"Could not run {cmd}") from ex

    @staticmethod
    def _start_logging_thread(stream, logger_name):
        thread = threading.Thread(target=async_log, args=(stream, logger_name))
        thread.start()
        return thread

    @staticmethod
    def _start_loggers(stdout, stderr, logger_name):
        """Starts log capturing in separate threads"""
        return BaseEnvironment._start_logging_thread(stdout, logger_name), BaseEnvironment._start_logging_thread(
            stderr, logger_name
        )


class NoSandbox(BaseEnvironment):
    """Default wrapper for application

    Runs the application without any sandboxing
    """

    def start(self, path, args, cwd):
        """
        Start the passed in binary at 'path' using arguments 'args' in directory 'cwd'.
        Return a tuple containing spawned processes and hooked output threads.
        :param path: string with relative path to the binary
        :param args: array of string arguments to be passed to the binary
        :param cwd: string directory to start the process in
        :return: tuple containing:
            - parent process: (psutil.POpen, superset of psutil.Process), target binary process
            - child process: since no sandboxing is used, this process is the same as parent
            - stdout thread: spawned thread reading from binary stdout stream
            - stderr thread: spawned thread reading from binary stderr stream
        :raise: SctfRuntimeError if the target 'path' is not a valid executable
        """
        if not is_file_executable(path):
            raise SctfRuntimeError(f"File is not a valid executable: {path}")

        proc, stdout_thread, stderr_thread = super().start_internal(path, args, LINE_BUFFER, os.path.basename(path))
        # The proc is not running in a sandbox and the child process (second return argument)
        # is the same as the parent process
        # Note:
        #   Second returned argument is of type psutil.Popen: according to docs, this class contains
        #    the same functionality as subprocess.Process class, in case of name clashes: psutil.Process
        #    implementation takes precedence - in effect it will behave *just like* psutil.Process.
        #   This is important as the BwrapSandbox.start(...) returns psutil.Process as its second argument.
        return proc, proc, stdout_thread, stderr_thread


class BwrapSandbox(BaseEnvironment):
    """Sandboxes application inside bwrap"""

    def start(self, path, args, cwd):
        """
        Start the passed in binary at 'path' using arguments 'args' in directory 'cwd'.
        Return a tuple containing spawned processes and hooked output threads.
        :param path: string with either absolute or relative path, will be prefixed with sandbox directory
        :param args: array of string arguments to be passed to the binary
        :param cwd: string directory to start the process in, relative to the sandbox directory
        :return: tuple containing:
            - parent process: (psutil.Popen, superset of psutil.Process), this is the bubblewrap/sandbox process
            - child process: (psutil.Process), this is the binary process (or None if finished before could be found)
            - stdout thread: spawned thread reading from binary stdout stream
            - stderr thread: spawned thread reading from binary stderr stream
        """
        self._check_binary_path(path, cwd)

        logger_name = os.path.basename(path)
        parent_proc, stdout_thread, stderr_thread = super().start_internal(
            path, args, self._define_cmd(self.environment, cwd, path, self.extra_mount_list), logger_name
        )

        # Note: If the child process is already terminated, there is no way of finding it
        #   - assume None means successful execution.
        # TODO: bwrap reports the PID of the wrapped process, so we always know what the PID is/was, see: SPPAD-59642
        child_proc = None
        try:
            child_proc = self._find_application(parent_proc, path)
        except SctfRuntimeError:
            assert parent_proc.is_running(), (
                "Child could not be found, since parent process is not running, assuming error"
            )
        return parent_proc, child_proc, stdout_thread, stderr_thread

    @staticmethod
    @tenacity.retry(
        wait=tenacity.wait_fixed(sctf_config.RETRY_DELAY_S),
        stop=tenacity.stop_after_attempt(sctf_config.RETRY_COUNT),
        reraise=True,
    )
    def _find_application(target_process, target_path):
        def find_process_in_tree(proc):
            for child_proc in proc.children():
                if os.path.basename(child_proc.exe()) == os.path.basename(target_path):
                    return child_proc

                # valgrind case
                if "valgrind" in child_proc.cmdline() and target_path in child_proc.cmdline():
                    return child_proc

                if child_proc.children():
                    return find_process_in_tree(child_proc)

            return None

        target_child = find_process_in_tree(target_process)
        if target_child:
            return target_child
        if target_process.poll() is not None:
            return None
        raise SctfRuntimeError(f"Could not find the the target process' child with path: {target_path}")

    @staticmethod
    def _does_path_include_run_under_apps(path):
        """
        Check whether the path argument contains one of short app names set in config file.
        Return True if yes, meaning the current path points to an app that should have run_under enabled.
        """
        for app in sctf_config.RUN_APPS_UNDER_LIST:
            if app in path:
                return True
        return False

    @staticmethod
    def _define_cmd(environment, cwd, path, extra_mount_list):
        if BwrapSandbox._does_path_include_run_under_apps(path):
            return BwrapSandbox._bwrap_cmd(environment, cwd, extra_mount_list) + LINE_BUFFER + BwrapSandbox._run_under()
        return BwrapSandbox._bwrap_cmd(environment, cwd, extra_mount_list) + LINE_BUFFER

    @staticmethod
    # TEST_PREMATURE_EXIT_FILE needs to be set correctly in order to execute a gtest in bwrap. Otherwise
    # there will a segmentation fault in gtest.cc, because the file can not be created.
    def _bwrap_cmd(environment, cwd, extra_mount_list):
        cmd = [
            "/usr/bin/bwrap",
            "--die-with-parent",
            f"--bind {environment.tmp_sysroot} /",
            f"--bind {environment.tmp_workspace} /tmp",
            f"--bind {environment.tmp_persistent} /persistent",
            "--ro-bind /bin /bin",
            "--ro-bind /lib /lib",
            "--ro-bind /lib64 /lib64",
            "--ro-bind /usr/lib /usr/lib",
            "--ro-bind /usr/bin /usr/bin",
            f"--bind {environment.artifact_output_path} /tmp/artifacts",
            f"--chdir {cwd}",
            "--proc /proc",
            "--dev-bind /dev /dev",  # @todo: fix shm sharing
            "--setenv TEST_PREMATURE_EXIT_FILE /tmp/gtest.exited_prematurely",
            "--setenv SCTF SCTF",
            "--setenv AMSR_DISABLE_INTEGRITY_CHECK 1",
        ]

        solibs_path = os.environ.get("SOLIBS_PATH")
        if solibs_path:
            cmd.append(f"--ro-bind {environment.bazel_solibs.src} {environment.bazel_solibs.dst}")
            cmd.append(f"--setenv LD_LIBRARY_PATH {solibs_path}")

        if os.path.isdir("/usr/lib64"):
            cmd.append("--ro-bind /usr/lib64 /usr/lib64")

        if os.path.isdir("/usr/libexec"):
            cmd.append("--ro-bind /usr/libexec /usr/libexec")

        if extra_mount_list and environment.extra_mount_list:
            extra_mount_list += environment.extra_mount_list
        elif environment.extra_mount_list:
            extra_mount_list = environment.extra_mount_list

        if extra_mount_list:
            for extra_data in extra_mount_list:
                if (
                    isinstance(extra_data[0], str)
                    and os.path.isdir(extra_data[0])
                    and isinstance(extra_data[1], str)
                    and os.path.isabs(extra_data[1])
                ):
                    # Allowing extra mounts to be configured as read-only
                    if (len(extra_data) >= 3) and isinstance(extra_data[2], bool) and extra_data[2]:
                        cmd.append(f"--ro-bind {extra_data[0]} {extra_data[1]}")
                    else:
                        cmd.append(f"--bind {extra_data[0]} {extra_data[1]}")
                else:
                    raise SctfRuntimeError(f"Extra bounding data {extra_data} is not valid")

        return " ".join(cmd).split()

    @staticmethod
    def _run_under():
        return sctf_config.RUN_APPS_UNDER_TOOL.split()

    def _check_binary_path(self, path, cwd):
        sandboxed_path = self.environment.tmp_sysroot

        def append_path(current_path, added_path):
            if os.path.isabs(added_path):
                return current_path + added_path
            return os.path.join(current_path, added_path)

        sandboxed_path = append_path(sandboxed_path, cwd)
        sandboxed_path = append_path(sandboxed_path, path)

        if not is_file_executable(sandboxed_path):
            try:
                os.chmod(sandboxed_path, stat.S_IXOTH)
            except Exception as original_exception:
                raise SctfRuntimeError(f"File is not a valid executable: {sandboxed_path}") from original_exception
