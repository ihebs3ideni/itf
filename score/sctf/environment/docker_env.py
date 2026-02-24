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
"""Docker-based execution environment.

Implements the :class:`Environment` interface by delegating container
management to :class:`~score.itf.core.docker.DockerContainer`.  This layer
adds structured process tracking (``ProcessHandle``) and the
``Environment`` lifecycle contract on top of the shared Docker abstraction.

Construction::

    env = DockerEnvironment.from_image(
        "sctf:my_test",
        bootstrap_command="path/to/image_tarball",
    )
"""

import logging
import os
import threading

from score.itf.core.docker import DockerContainer, get_docker_client
from score.sctf.environment.base import Environment, ProcessHandle
from score.sctf.exception import SctfRuntimeError

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 15.0


def _async_log(gen, logger_name):
    """Read demuxed (stdout, stderr) chunks from a Docker exec stream and log them.

    Mirrors the ``_async_log`` pattern used by the bwrap/noop backends in SPP,
    adapted for Docker's demuxed generator which yields ``(stdout_bytes, stderr_bytes)``
    tuples.
    """
    log = logging.getLogger(logger_name)
    try:
        for stdout_chunk, stderr_chunk in gen:
            if stdout_chunk:
                for line in stdout_chunk.decode("utf-8", errors="replace").splitlines():
                    log.info(line)
            if stderr_chunk:
                for line in stderr_chunk.decode("utf-8", errors="replace").splitlines():
                    log.warning(line)
    except ValueError:
        pass  # stream closed


class DockerEnvironment(Environment):
    """Run binaries inside a Docker container.

    Delegates container lifecycle and command execution to
    :class:`~score.itf.core.docker.DockerContainer` and adds
    process-handle tracking required by the ``Environment`` ABC.

    Parameters:
        image: Docker image name/tag to use.
        mounts: ``{container_path: host_path}`` dictionary for bind mounts.
        env_vars: Extra environment variables inside the container.
        bootstrap_command: Optional shell command to run before container start
            (e.g. the ``oci_load`` script that runs ``docker load``).
        privileged: Whether the container runs in privileged mode.
        network_mode: Docker network mode (``"bridge"``, ``"host"``, etc.).
        command: Command to keep the container alive (default: ``"sleep infinity"``).
        shm_size: Shared memory size (default: ``"2G"``).
        timeout: Default process stop timeout in seconds.
    """

    def __init__(
        self,
        *,
        image=None,
        mounts=None,
        env_vars=None,
        bootstrap_command=None,
        privileged=False,
        network_mode="bridge",
        command="sleep infinity",
        shm_size="2G",
        timeout=_DEFAULT_TIMEOUT,
    ):
        if not image:
            raise ValueError("'image' must be provided.")

        self._image = image
        self._mounts = mounts or {}
        self._env_vars = env_vars or {}
        self._bootstrap_command = bootstrap_command
        self._privileged = privileged
        self._network_mode = network_mode
        self._command = command
        self._shm_size = shm_size
        self._timeout = timeout

        self._docker = None  # DockerContainer instance

    # ------------------------------------------------------------------
    # Alternative constructor
    # ------------------------------------------------------------------

    @classmethod
    def from_image(
        cls,
        image,
        *,
        bootstrap_command=None,
        mounts=None,
        env_vars=None,
        privileged=False,
        network_mode="bridge",
        command="sleep infinity",
        shm_size="2G",
        timeout=_DEFAULT_TIMEOUT,
    ):
        """Create an environment from a pre-built Docker image."""
        return cls(
            image=image,
            bootstrap_command=bootstrap_command,
            mounts=mounts,
            env_vars=env_vars,
            privileged=privileged,
            network_mode=network_mode,
            command=command,
            shm_size=shm_size,
            timeout=timeout,
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def setup(self):
        client = get_docker_client()

        # Build volume mounts in Docker SDK format
        volumes = {}
        for container_path, host_path in self._mounts.items():
            volumes[host_path] = {"bind": container_path, "mode": "rw"}

        # Build environment variables
        env = dict(self._env_vars)
        env.setdefault("LD_LIBRARY_PATH", "/usr/bazel/lib")

        self._docker = DockerContainer.run(
            client,
            image=self._image,
            command=self._command,
            environment=env,
            volumes=volumes or None,
            privileged=self._privileged,
            network_mode=self._network_mode,
            shm_size=self._shm_size,
            bootstrap_command=self._bootstrap_command,
        )

    def teardown(self):
        if self._docker:
            self._docker.stop(timeout=2)
            self._docker = None

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def execute(self, path, args, cwd="/"):
        if not self._docker:
            raise SctfRuntimeError("Environment not set up — call setup() first.")

        cmd = [path] + args
        logger.info("Executing in container: %s (cwd=%s)", cmd, cwd)

        exec_id, output = self._docker.exec(
            cmd, workdir=cwd, environment=self._env_vars, stream=True,
        )

        logger_name = os.path.basename(path)
        stdout_thread = self._start_logging_thread(output, logger_name)

        return ProcessHandle(
            pid=None,
            parent=exec_id,
            stdout_thread=stdout_thread,
            _metadata={"container_id": self._docker.id},
        )

    def stop_process(self, handle, timeout=None):
        timeout = timeout if timeout is not None else self._timeout
        exec_id = handle.parent

        # Try to wait for natural completion first
        exit_code = self._docker.wait_exec(exec_id, timeout=timeout)
        if exit_code is not None:
            handle.exit_code = exit_code
            self._join_output_threads(handle, timeout=5.0)
            return exit_code

        # Timeout — escalate to kill
        exit_code = self._docker.kill_exec(exec_id)
        handle.exit_code = exit_code
        self._join_output_threads(handle, timeout=2.0)
        return exit_code

    @staticmethod
    def _start_logging_thread(stream, logger_name):
        """Spawn a daemon thread that reads *stream* and logs via *logger_name*."""
        thread = threading.Thread(
            target=_async_log, args=(stream, logger_name), daemon=True,
        )
        thread.start()
        return thread

    @staticmethod
    def _join_output_threads(handle, timeout=5.0):
        """Wait for stdout/stderr reader threads to finish flushing."""
        for t in (handle.stdout_thread, handle.stderr_thread):
            if t is not None and t.is_alive():
                t.join(timeout=timeout)

    def is_process_running(self, handle):
        if handle.exit_code is not None:
            return False
        if not handle.parent:
            return False
        return self._docker.is_exec_running(handle.parent)

    # ------------------------------------------------------------------
    # File transfer
    # ------------------------------------------------------------------

    def copy_to(self, host_path, env_path):
        if not self._docker:
            raise SctfRuntimeError("Environment not set up.")
        self._docker.copy_to(host_path, env_path)

    def copy_from(self, env_path, host_path):
        if not self._docker:
            raise SctfRuntimeError("Environment not set up.")
        self._docker.copy_from(env_path, host_path)

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    @property
    def container(self):
        """The underlying Docker container object (or ``None``)."""
        return self._docker.raw if self._docker else None

    @property
    def docker_container(self):
        """The :class:`DockerContainer` instance (or ``None``)."""
        return self._docker
