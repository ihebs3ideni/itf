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

Implements the :class:`Environment` interface using the Docker Python SDK.
This backend can be used by both ITF (integration tests with pre-built images)
and SCTF (component tests with tarball-derived images), providing a unified
container runtime for all test types.

Two construction modes:

1. **From an existing image** (ITF-style)::

       env = DockerEnvironment.from_image("ubuntu:24.04")

2. **From a host sysroot directory** (SCTF-style)::

       env = DockerEnvironment.from_sysroot("/tmp/abc123",
           mounts={"/tmp": workspace, "/persistent": persistent})

   A temporary Docker image is created by tarring the sysroot and importing it.
"""

import io
import logging
import os
import shutil
import subprocess
import tarfile
import tempfile
import time
from typing import Optional

from score.itf.core.environment.base import Environment, ProcessHandle

logger = logging.getLogger(__name__)


def _get_docker_client():
    """Create a Docker client, working around the requests/urllib3 version conflict.

    The system-installed ``docker`` SDK (5.x) uses ``http+docker://`` as the URL
    scheme for Unix socket communication.  If a newer ``requests`` (>=2.32) is
    installed (e.g. in ``~/.local``), its ``HTTPAdapter.get_connection_with_tls_context``
    rejects that scheme.  We detect this situation and patch the adapter so that
    the Unix-socket transport works correctly.
    """
    import docker as pypi_docker  # local import to allow patching first

    try:
        return pypi_docker.from_env()
    except pypi_docker.errors.DockerException as exc:
        if "http+docker" not in str(exc):
            raise

    # --- Apply compatibility patch -------------------------------------------
    logger.debug("Applying http+docker compatibility patch for docker SDK / requests")
    import requests.adapters
    from docker.transport import UnixHTTPAdapter

    _orig = requests.adapters.HTTPAdapter.get_connection_with_tls_context

    def _patched(self, request, verify, proxies=None, cert=None):
        if isinstance(self, UnixHTTPAdapter):
            # UnixHTTPAdapter overrides ``send()`` completely and never uses the
            # poolmanager, so we can return a dummy connection.
            return self.get_connection(request.url, proxies)
        return _orig(self, request, verify, proxies, cert)

    requests.adapters.HTTPAdapter.get_connection_with_tls_context = _patched
    return pypi_docker.from_env()

_DEFAULT_TIMEOUT = 15.0


class DockerEnvironment(Environment):
    """Run binaries inside a Docker container.

    Parameters:
        image: Docker image name/tag to use.
        sysroot: If set, a host directory to ``docker import`` as the image.
        mounts: ``{container_path: host_path}`` dictionary for bind mounts.
        env_vars: Extra environment variables inside the container.
        bootstrap_command: Optional shell command to run before container start
            (e.g. ``docker load -i image.tar``).
        privileged: Whether the container runs in privileged mode
            (needed for ``/dev`` access).
        network_mode: Docker network mode (``"bridge"``, ``"host"``, etc.).
        timeout: Default process stop timeout in seconds.
    """

    def __init__(
        self,
        *,
        image: Optional[str] = None,
        sysroot: Optional[str] = None,
        mounts: Optional[dict[str, str]] = None,
        env_vars: Optional[dict[str, str]] = None,
        bootstrap_command: Optional[str] = None,
        privileged: bool = False,
        network_mode: str = "bridge",
        timeout: float = _DEFAULT_TIMEOUT,
    ):
        if not image and not sysroot:
            raise ValueError("Either 'image' or 'sysroot' must be provided.")

        self._image = image
        self._sysroot = sysroot
        self._mounts = mounts or {}
        self._env_vars = env_vars or {}
        self._bootstrap_command = bootstrap_command
        self._privileged = privileged
        self._network_mode = network_mode
        self._timeout = timeout

        self._client = None  # docker.DockerClient, set in setup()
        self._container = None
        self._tmp_image_tag: str | None = None  # Track images we create so we can clean up

    # ------------------------------------------------------------------
    # Alternative constructors
    # ------------------------------------------------------------------

    @classmethod
    def from_image(
        cls,
        image: str,
        *,
        bootstrap_command: Optional[str] = None,
        mounts: Optional[dict[str, str]] = None,
        env_vars: Optional[dict[str, str]] = None,
        privileged: bool = False,
        network_mode: str = "bridge",
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> "DockerEnvironment":
        """Create an environment from an existing Docker image (ITF-style)."""
        return cls(
            image=image,
            bootstrap_command=bootstrap_command,
            mounts=mounts,
            env_vars=env_vars,
            privileged=privileged,
            network_mode=network_mode,
            timeout=timeout,
        )

    @classmethod
    def from_sysroot(
        cls,
        sysroot: str,
        *,
        mounts: Optional[dict[str, str]] = None,
        env_vars: Optional[dict[str, str]] = None,
        privileged: bool = False,
        network_mode: str = "bridge",
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> "DockerEnvironment":
        """Create an environment by importing a host sysroot directory (SCTF-style).

        The sysroot is packed into a tar and fed to ``docker import`` to produce
        a transient image.
        """
        return cls(
            sysroot=sysroot,
            mounts=mounts,
            env_vars=env_vars,
            privileged=privileged,
            network_mode=network_mode,
            timeout=timeout,
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def setup(self) -> None:
        self._client = _get_docker_client()

        # Optional pre-bootstrap (e.g. docker load)
        if self._bootstrap_command:
            logger.info("Running bootstrap: %s", self._bootstrap_command)
            subprocess.run(self._bootstrap_command, shell=True, check=True)

        # If we have a sysroot but no image, import it
        if self._sysroot and not self._image:
            self._image = self._import_sysroot(self._sysroot)
            self._tmp_image_tag = self._image

        # Build volume mounts
        volumes = {}
        for container_path, host_path in self._mounts.items():
            volumes[host_path] = {"bind": container_path, "mode": "rw"}

        # Build environment
        env = dict(self._env_vars)
        env.setdefault("SCTF", "SCTF")
        env.setdefault("AMSR_DISABLE_INTEGRITY_CHECK", "1")
        env.setdefault("TEST_PREMATURE_EXIT_FILE", "/tmp/gtest.exited_prematurely")

        logger.info("Starting container from image %s", self._image)
        self._container = self._client.containers.run(
            self._image,
            command="sleep infinity",
            detach=True,
            auto_remove=True,
            init=True,
            volumes=volumes or None,
            environment=env,
            privileged=self._privileged,
            network_mode=self._network_mode,
        )
        logger.info("Container started: %s", self._container.short_id)

    def teardown(self) -> None:
        if self._container:
            try:
                self._container.stop(timeout=2)
            except Exception:  # noqa: BLE001
                logger.debug("Container stop failed (may already be removed)", exc_info=True)
            self._container = None

        # Clean up the transient image if we created one
        if self._tmp_image_tag and self._client:
            try:
                self._client.images.remove(self._tmp_image_tag, force=True)
            except Exception:  # noqa: BLE001
                logger.debug("Could not remove tmp image %s", self._tmp_image_tag, exc_info=True)
            self._tmp_image_tag = None

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def execute(self, path: str, args: list[str], cwd: str = "/") -> ProcessHandle:
        if not self._container:
            raise RuntimeError("Environment not set up — call setup() first.")

        cmd = [path] + args
        logger.info("Executing in container: %s (cwd=%s)", cmd, cwd)

        # Docker exec_run is synchronous by default — run in detached (stream) mode
        # so we can return a handle without blocking.
        exec_id = self._client.api.exec_create(
            self._container.id,
            cmd,
            workdir=cwd,
            environment=self._env_vars,
        )
        self._client.api.exec_start(exec_id["Id"], detach=True)

        handle = ProcessHandle(
            pid=None,  # Docker doesn't expose PID the same way
            parent=exec_id["Id"],
            _metadata={"container_id": self._container.id},
        )
        return handle

    def stop_process(self, handle: ProcessHandle, timeout: float | None = None) -> int:
        """Stop a process started via ``exec``.

        Docker exec doesn't provide a direct kill mechanism per-exec, so we
        inspect the exec and return its exit code. If still running, we signal
        via ``docker exec kill``.
        """
        timeout = timeout if timeout is not None else self._timeout
        exec_id = handle.parent

        # Poll for completion
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            info = self._client.api.exec_inspect(exec_id)
            if not info["Running"]:
                handle.exit_code = info["ExitCode"]
                return handle.exit_code
            time.sleep(0.2)

        # Timeout: try to kill the process inside the container via its PID
        info = self._client.api.exec_inspect(exec_id)
        pid_inside = info.get("Pid", 0)
        if pid_inside and self._container:
            try:
                self._container.exec_run(f"kill -9 {pid_inside}")
            except Exception:  # noqa: BLE001
                pass

        # Wait briefly for the kill to take effect, then re-inspect
        kill_deadline = time.monotonic() + 5
        while time.monotonic() < kill_deadline:
            info = self._client.api.exec_inspect(exec_id)
            if not info["Running"]:
                break
            time.sleep(0.2)

        exit_code = info.get("ExitCode")
        # ExitCode can be None if Docker couldn't determine it — treat as killed
        handle.exit_code = exit_code if exit_code is not None else -9
        return handle.exit_code

    def is_process_running(self, handle: ProcessHandle) -> bool:
        if not handle.parent:
            return False
        try:
            info = self._client.api.exec_inspect(handle.parent)
            return info["Running"]
        except Exception:  # noqa: BLE001
            return False

    # ------------------------------------------------------------------
    # File transfer
    # ------------------------------------------------------------------

    def copy_to(self, host_path: str, env_path: str) -> None:
        if not self._container:
            raise RuntimeError("Environment not set up.")

        tar_stream = io.BytesIO()
        with tarfile.open(fileobj=tar_stream, mode="w") as tar:
            tar.add(host_path, arcname=os.path.basename(env_path))
        tar_stream.seek(0)
        self._container.put_archive(os.path.dirname(env_path) or "/", tar_stream)

    def copy_from(self, env_path: str, host_path: str) -> None:
        if not self._container:
            raise RuntimeError("Environment not set up.")

        bits, _ = self._container.get_archive(env_path)
        tar_stream = io.BytesIO()
        for chunk in bits:
            tar_stream.write(chunk)
        tar_stream.seek(0)

        os.makedirs(os.path.dirname(host_path) or ".", exist_ok=True)
        with tarfile.open(fileobj=tar_stream) as tar:
            tar.extractall(path=os.path.dirname(host_path) or ".")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _import_sysroot(self, sysroot: str) -> str:
        """Create a Docker image from a host sysroot directory via ``docker import``."""
        tag = f"sctf-sysroot:{os.path.basename(sysroot)}"
        logger.info("Importing sysroot %s as Docker image %s", sysroot, tag)

        # Create a tar of the sysroot and pipe to docker import
        with tempfile.NamedTemporaryFile(suffix=".tar", delete=False) as tmp:
            tmp_tar = tmp.name

        try:
            with tarfile.open(tmp_tar, "w") as tar:
                tar.add(sysroot, arcname=".")

            self._client.api.import_image(
                src=tmp_tar,
                repository=tag.split(":")[0],
                tag=tag.split(":")[1],
            )
        finally:
            os.unlink(tmp_tar)

        return tag
