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
"""Shared Docker container management for the ITF ecosystem.

Provides :class:`DockerContainer` — a single, reusable abstraction over the
Docker Python SDK for container lifecycle, command execution, network
inspection, and file transfer.  Both the ITF Docker plugin and the SCTF
Docker environment delegate to this class instead of calling ``docker-py``
directly.

Example::

    from score.itf.core.docker import DockerContainer, get_docker_client

    client = get_docker_client()
    container = DockerContainer.run(
        client,
        image="ubuntu:24.04",
        command="sleep infinity",
    )
    result = container.exec(["echo", "hello"])
    container.stop()
"""

import io
import logging
import os
import subprocess
import tarfile
import time

logger = logging.getLogger(__name__)

# Silence urllib3 noise coming from the Docker SDK
logging.getLogger("urllib3").setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# Client factory
# ---------------------------------------------------------------------------

def get_docker_client():
    """Create a Docker client, applying a compatibility patch if required.

    The ``docker`` SDK (5.x / 7.x) uses ``http+docker://`` as the URL scheme
    for Unix-socket communication.  Newer versions of ``requests`` (>=2.32)
    reject that scheme in ``HTTPAdapter.get_connection_with_tls_context``.
    This helper detects the situation and monkey-patches the adapter so that
    everything works regardless of the installed ``requests`` version.
    """
    import docker as pypi_docker  # pylint: disable=import-outside-toplevel

    try:
        return pypi_docker.from_env()
    except pypi_docker.errors.DockerException as exc:
        if "http+docker" not in str(exc):
            raise

    # --- Apply compatibility patch ------------------------------------------
    logger.debug("Applying http+docker compatibility patch for docker SDK / requests")
    import requests.adapters  # pylint: disable=import-outside-toplevel
    from docker.transport import UnixHTTPAdapter  # pylint: disable=import-outside-toplevel

    _orig = requests.adapters.HTTPAdapter.get_connection_with_tls_context

    def _patched(self, request, verify, proxies=None, cert=None):
        if isinstance(self, UnixHTTPAdapter):
            return self.get_connection(request.url, proxies)
        return _orig(self, request, verify, proxies, cert)

    requests.adapters.HTTPAdapter.get_connection_with_tls_context = _patched
    return pypi_docker.from_env()


# ---------------------------------------------------------------------------
# DockerContainer
# ---------------------------------------------------------------------------

class DockerContainer:
    """Thin, reusable wrapper around a running Docker container.

    Responsibilities:
      - Container lifecycle (start / stop)
      - Command execution (``exec``)
      - Process polling (``is_exec_running``, ``wait_exec``)
      - Network inspection (``get_ip``, ``get_gateway``)
      - File transfer (``copy_to``, ``copy_from``)

    This class is deliberately **framework-agnostic** — it knows nothing about
    pytest fixtures, the ``Target`` class, or the ``Environment`` ABC.  Those
    are layered on top by consumers (ITF plugin, SCTF environment).
    """

    def __init__(self, client, container):
        self._client = client
        self._container = container

    # ------------------------------------------------------------------
    # Alternative constructors
    # ------------------------------------------------------------------

    @classmethod
    def run(
        cls,
        client,
        image,
        *,
        command="sleep infinity",
        environment=None,
        volumes=None,
        privileged=False,
        network_mode="bridge",
        shm_size=None,
        init=True,
        auto_remove=True,
        bootstrap_command=None,
    ):
        """Create and start a new container.

        Args:
            client: A ``docker.DockerClient`` (from :func:`get_docker_client`).
            image: Image name/tag.
            command: Keep-alive command (default ``"sleep infinity"``).
            environment: ``dict`` of environment variables.
            volumes: Docker-SDK style volumes dict, e.g.
                ``{"/host/path": {"bind": "/container/path", "mode": "rw"}}``.
            privileged: Run in privileged mode.
            network_mode: ``"bridge"``, ``"host"``, etc.
            shm_size: Shared memory size string (e.g. ``"2G"``).
            init: Use ``docker --init`` (tini) inside the container.
            auto_remove: Remove container on stop.
            bootstrap_command: Optional shell command (e.g. ``docker load``) to
                run on the **host** before starting the container.

        Returns:
            A :class:`DockerContainer` wrapping the started container.
        """
        if bootstrap_command:
            logger.info("Running bootstrap: %s", bootstrap_command)
            subprocess.run([bootstrap_command], check=True)

        kwargs = dict(
            command=command,
            detach=True,
            auto_remove=auto_remove,
            init=init,
        )
        if environment:
            kwargs["environment"] = environment
        if volumes:
            kwargs["volumes"] = volumes
        if privileged:
            kwargs["privileged"] = True
        if network_mode:
            kwargs["network_mode"] = network_mode
        if shm_size:
            kwargs["shm_size"] = shm_size

        logger.info("Starting container from image %s", image)
        container = client.containers.run(image, **kwargs)
        logger.info("Container started: %s", container.short_id)
        return cls(client, container)

    @classmethod
    def from_raw(cls, client, container):
        """Wrap an existing ``docker-py`` ``Container`` object.

        Useful when the container is created elsewhere (e.g. a legacy fixture)
        and you want to access the helper methods on this class.
        """
        return cls(client, container)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def stop(self, timeout=2):
        """Stop (and auto-remove if configured) the container."""
        if self._container:
            try:
                self._container.stop(timeout=timeout)
            except Exception:
                logger.debug("Container stop failed (may already be removed)", exc_info=True)
            self._container = None

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def exec(self, cmd, *, workdir="/", environment=None, detach=True, stream=False):
        """Run *cmd* inside the container via ``docker exec``.

        Args:
            cmd: Command as a list of strings.
            workdir: Working directory inside the container.
            environment: Extra env vars for this exec invocation.
            detach: If ``True`` (default), return immediately with an exec-ID
                string.  If ``False``, block and return ``(exit_code, output)``.
            stream: If ``True``, return ``(exec_id, output_generator)`` where
                the generator yields ``(stdout_bytes, stderr_bytes)`` tuples.
                The caller is responsible for consuming the generator.

        Returns:
            * **detach=True** — The Docker exec-ID (``str``).
            * **detach=False** — A ``(exit_code, output)`` tuple.
            * **stream=True** — A ``(exec_id, generator)`` tuple.
        """
        if not self._container:
            raise RuntimeError("Container is not running.")

        if stream:
            exec_id = self._client.api.exec_create(
                self._container.id,
                cmd,
                workdir=workdir,
                environment=environment,
                stdout=True,
                stderr=True,
            )
            eid = exec_id["Id"]
            output = self._client.api.exec_start(eid, stream=True, demux=True)
            return eid, output

        if detach:
            exec_id = self._client.api.exec_create(
                self._container.id,
                cmd,
                workdir=workdir,
                environment=environment,
            )
            self._client.api.exec_start(exec_id["Id"], detach=True)
            return exec_id["Id"]

        # Synchronous mode — uses the high-level SDK for simplicity
        return self._container.exec_run(cmd, workdir=workdir, environment=environment)

    def exec_inspect(self, exec_id):
        """Return the raw ``exec_inspect`` dict for *exec_id*."""
        return self._client.api.exec_inspect(exec_id)

    def is_exec_running(self, exec_id):
        """Return ``True`` if the exec identified by *exec_id* is still running."""
        if not exec_id:
            return False
        try:
            return self._client.api.exec_inspect(exec_id)["Running"]
        except Exception:
            return False

    def wait_exec(self, exec_id, timeout=15.0, poll_interval=0.2):
        """Block until exec *exec_id* finishes or *timeout* expires.

        Returns:
            The exit code (``int``), or ``None`` if it timed out.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            info = self._client.api.exec_inspect(exec_id)
            if not info["Running"]:
                return info["ExitCode"]
            time.sleep(poll_interval)
        return None

    def kill_exec(self, exec_id, signal=9):
        """Attempt to kill the process behind *exec_id* inside the container.

        Docker doesn't expose a direct ``exec kill`` API, so this inspects the
        exec for its PID and sends a signal via ``kill`` inside the container.

        Returns:
            The exit code after waiting briefly, or ``-9`` on failure.
        """
        info = self._client.api.exec_inspect(exec_id)
        pid_inside = info.get("Pid", 0)
        if pid_inside and self._container:
            try:
                self._container.exec_run(f"kill -{signal} {pid_inside}")
            except Exception:
                pass

        # Wait briefly for the kill to take effect
        exit_code = self.wait_exec(exec_id, timeout=5.0)
        return exit_code if exit_code is not None else -9

    # ------------------------------------------------------------------
    # Network inspection
    # ------------------------------------------------------------------

    def reload(self):
        """Refresh container metadata from the daemon."""
        if self._container:
            self._container.reload()

    def get_ip(self, network="bridge"):
        """Return the container's IP address on *network*."""
        self.reload()
        return self._container.attrs["NetworkSettings"]["Networks"][network]["IPAddress"]

    def get_gateway(self, network="bridge"):
        """Return the gateway address for *network*."""
        self.reload()
        return self._container.attrs["NetworkSettings"]["Networks"][network]["Gateway"]

    # ------------------------------------------------------------------
    # File transfer
    # ------------------------------------------------------------------

    def copy_to(self, host_path, container_path):
        """Copy a file or directory from the host **into** the container.

        Uses Docker's ``put_archive`` API with an in-memory tar stream.
        """
        if not self._container:
            raise RuntimeError("Container is not running.")

        tar_stream = io.BytesIO()
        with tarfile.open(fileobj=tar_stream, mode="w") as tar:
            tar.add(host_path, arcname=os.path.basename(container_path))
        tar_stream.seek(0)
        self._container.put_archive(os.path.dirname(container_path) or "/", tar_stream)

    def copy_from(self, container_path, host_path):
        """Copy a file or directory **out of** the container to the host.

        Uses Docker's ``get_archive`` API.
        """
        if not self._container:
            raise RuntimeError("Container is not running.")

        bits, _ = self._container.get_archive(container_path)
        tar_stream = io.BytesIO()
        for chunk in bits:
            tar_stream.write(chunk)
        tar_stream.seek(0)

        os.makedirs(os.path.dirname(host_path) or ".", exist_ok=True)
        with tarfile.open(fileobj=tar_stream) as tar:
            members = tar.getmembers()
            if len(members) == 1 and not members[0].isdir():
                # Single file: extract and rename to host_path
                f = tar.extractfile(members[0])
                if f is not None:
                    with open(host_path, "wb") as out:
                        out.write(f.read())
            else:
                tar.extractall(path=os.path.dirname(host_path) or ".")

    # ------------------------------------------------------------------
    # Raw access
    # ------------------------------------------------------------------

    @property
    def raw(self):
        """The underlying ``docker.models.containers.Container`` object."""
        return self._container

    @property
    def id(self):
        """The full container ID."""
        return self._container.id if self._container else None

    @property
    def short_id(self):
        """The short container ID."""
        return self._container.short_id if self._container else None
