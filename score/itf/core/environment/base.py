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
"""Abstract base for execution environments (Docker, Bubblewrap, bare-metal)."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ProcessHandle:
    """Uniform handle returned by every environment backend after spawning a process.

    Attributes:
        pid: The process ID of the spawned application (inside or outside the sandbox).
             May be ``None`` when the process finished before it could be observed.
        exit_code: Set after the process terminates. ``None`` while still running.
        parent: Backend-specific parent process object (e.g. ``psutil.Popen`` for
                bwrap, Docker exec-id for Docker).
        child: Backend-specific child process object (e.g. ``psutil.Process`` for bwrap).
        stdout_thread: Thread capturing stdout, if applicable.
        stderr_thread: Thread capturing stderr, if applicable.
    """

    pid: Optional[int] = None
    exit_code: Optional[int] = None
    parent: object = None
    child: object = None
    stdout_thread: object = None
    stderr_thread: object = None
    _metadata: dict = field(default_factory=dict)


class Environment(ABC):
    """Common interface for isolated execution environments.

    Every concrete backend (Docker, Bubblewrap, no-sandbox) implements this
    interface so that higher-level code (``Process``, ``BaseSim``,
    ``basic_sandbox`` fixture) can remain backend-agnostic.

    Lifecycle::

        env = DockerEnvironment(config)   # or BwrapEnvironment, NoopEnvironment
        env.setup()                        # one-time heavy initialisation
        handle = env.execute(path, args)   # run a binary inside the environment
        env.stop_process(handle)           # stop that binary
        env.teardown()                     # destroy the environment
    """

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @abstractmethod
    def setup(self) -> None:
        """Prepare the environment (create container, extract sysroot, etc.).

        Called once before any ``execute()`` invocations.
        """

    @abstractmethod
    def teardown(self) -> None:
        """Destroy the environment and release all resources."""

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    @abstractmethod
    def execute(
        self,
        path: str,
        args: list[str],
        cwd: str = "/",
    ) -> ProcessHandle:
        """Run *path* with *args* inside the environment.

        Args:
            path: Absolute or relative path to the binary **inside** the environment.
            args: Command-line arguments forwarded to the binary.
            cwd:  Working directory inside the environment.

        Returns:
            A :class:`ProcessHandle` that the caller can use to track or stop the
            process.
        """

    @abstractmethod
    def stop_process(self, handle: ProcessHandle, timeout: float = 15.0) -> int:
        """Stop a previously started process.

        Args:
            handle: The handle returned by :meth:`execute`.
            timeout: Seconds to wait after SIGTERM before escalating to SIGKILL.

        Returns:
            The exit code of the process.
        """

    @abstractmethod
    def is_process_running(self, handle: ProcessHandle) -> bool:
        """Return ``True`` if the process tracked by *handle* is still alive."""

    # ------------------------------------------------------------------
    # File transfer
    # ------------------------------------------------------------------

    @abstractmethod
    def copy_to(self, host_path: str, env_path: str) -> None:
        """Copy a file or directory **into** the environment.

        Args:
            host_path: Absolute path on the host.
            env_path:  Destination path inside the environment.
        """

    @abstractmethod
    def copy_from(self, env_path: str, host_path: str) -> None:
        """Copy a file or directory **out of** the environment.

        Args:
            env_path:  Source path inside the environment.
            host_path: Destination path on the host.
        """

    # ------------------------------------------------------------------
    # Context-manager protocol
    # ------------------------------------------------------------------

    def __enter__(self):
        self.setup()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.teardown()
        return False
