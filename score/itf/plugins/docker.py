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
"""Docker pytest plugin for ITF integration tests.

Provides a single ``target`` fixture backed by :class:`DockerTarget` — a rich
wrapper around a Docker container that offers command execution (synchronous,
detached, streaming), process management, network inspection, file transfer,
and background log capture.

Also exports:

- :class:`DockerTcpDumpHandler` — :class:`~score.itf.core.com.tcpdump.TcpDumpHandler`
  implementation for Docker containers.
- :func:`get_docker_client` — factory with SDK compatibility patch.

The ``target`` fixture is activated automatically when a test requests it.
Its scope is determined dynamically by ``determine_target_scope``.
"""

import io
import logging
import os
import subprocess
import tarfile
import threading
import time

import pytest

from score.itf.plugins.core import determine_target_scope
from score.itf.plugins.core import Target
from score.itf.core.com.tcpdump import TcpDumpHandler


logger = logging.getLogger(__name__)

# Silence urllib3 noise coming from the Docker SDK
logging.getLogger("urllib3").setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# Docker client factory
# ---------------------------------------------------------------------------

def get_docker_client():
    """Create a Docker client, applying a compatibility patch if required.

    The ``docker`` SDK (7.x) uses ``http+docker://`` as the URL scheme
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
# Background output reader
# ---------------------------------------------------------------------------

class _OutputReader:
    """Drains a Docker exec output stream in a background daemon thread.

    Each line of stdout/stderr is forwarded to the Python ``logging`` system so
    that it appears in pytest's ``live log`` / captured output.
    """

    def __init__(self, exec_id, output_generator, cmd_label=None):
        self._exec_id = exec_id[:12]
        self._label = cmd_label or self._exec_id
        self._gen = output_generator
        self._lines: list[str] = []
        self._thread = threading.Thread(
            target=self._drain, name=f"exec-log-{self._exec_id}", daemon=True
        )
        self._thread.start()

    def _drain(self):
        try:
            for stdout_chunk, stderr_chunk in self._gen:
                for chunk, stream_name in ((stdout_chunk, "stdout"), (stderr_chunk, "stderr")):
                    if not chunk:
                        continue
                    for line in chunk.decode("utf-8", errors="replace").splitlines():
                        self._lines.append(line)
                        logger.info("[%s] %s", self._label, line)
        except Exception:
            logger.debug("Output reader for %s stopped", self._exec_id, exc_info=True)

    def join(self, timeout=2.0):
        """Wait for the reader thread to finish (call after exec exits)."""
        self._thread.join(timeout=timeout)

    @property
    def output(self):
        """All captured lines so far."""
        return list(self._lines)


# ---------------------------------------------------------------------------
# Docker TcpDump handler
# ---------------------------------------------------------------------------

class DockerTcpDumpHandler(TcpDumpHandler):
    """TcpDump handler for Docker containers.

    Uses ``exec()`` to start tcpdump, ``kill_exec()`` / ``wait_exec()``
    to stop it, and ``copy_from()`` to retrieve the pcap.
    """

    def __init__(self, docker_target):
        self._target = docker_target

    def start(self, cmd, container_pcap_path):
        return self._target.exec(cmd, detach=True)

    def stop(self, handle):
        self._target.kill_exec(handle, signal=15)
        self._target.wait_exec(handle, timeout=5.0)

    def retrieve(self, container_pcap_path, host_path):
        self._target.copy_from(container_pcap_path, host_path)


# ---------------------------------------------------------------------------
# CLI options
# ---------------------------------------------------------------------------

def pytest_addoption(parser):
    parser.addoption(
        "--docker-image",
        action="store",
        required=True,
        help="Docker image to run tests against.",
    )
    parser.addoption(
        "--docker-image-bootstrap",
        action="store",
        required=False,
        help="Docker image bootstrap command, that will be executed before referencing the container.",
    )


# ---------------------------------------------------------------------------
# DockerTarget
# ---------------------------------------------------------------------------

DOCKER_CAPABILITIES = ["exec"]


class DockerTarget(Target):
    """ITF target backed by a Docker container.

    Wraps a raw ``docker-py`` container and exposes:

    - **Execution**: :meth:`exec` (sync / detach / stream), :meth:`exec_inspect`,
      :meth:`is_exec_running`, :meth:`wait_exec`, :meth:`get_exec_output`,
      :meth:`kill_exec`.
    - **Network**: :meth:`get_ip`, :meth:`get_gateway`.
    - **File transfer**: :meth:`copy_to`, :meth:`copy_from`.
    - **SSH**: :meth:`ssh`.
    - **Lifecycle**: :meth:`stop`.

    All other ``docker-py`` container attributes (e.g. ``logs()``,
    ``reload()``, ``attrs``, ``id``, ``status``) are available directly
    via ``__getattr__`` delegation.
    """

    def __init__(self, client, container, capabilities=DOCKER_CAPABILITIES):
        super().__init__(capabilities=capabilities)
        self._client = client
        self._container = container
        self._output_readers: dict[str, _OutputReader] = {}

    def __getattr__(self, name):
        """Delegate attribute access to the underlying Docker container.

        This exposes all ``docker-py`` container methods and properties
        (e.g. ``target.logs()``, ``target.attrs``, ``target.status``)
        directly on the target instance.
        """
        container = self.__dict__.get("_container")
        if container is None:
            raise AttributeError(
                f"'{type(self).__name__}' has no attribute '{name}' "
                f"(container is stopped)"
            )
        return getattr(container, name)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def stop(self, timeout=2):
        """Stop (and auto-remove if configured) the container."""
        if self._container:
            cid = self._container.short_id
            logger.info("Stopping container %s", cid)
            for reader in self._output_readers.values():
                reader.join(timeout=1.0)
            self._output_readers.clear()
            try:
                self._container.stop(timeout=timeout)
            except Exception:
                logger.debug("Container stop failed (may already be removed)", exc_info=True)
            self._container = None
            logger.info("Container %s stopped", cid)

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def exec(self, cmd, *, workdir="/", environment=None, detach=True, stream=False):
        """Run *cmd* inside the container via ``docker exec``.

        Args:
            cmd: Command as a list of strings (or a single string).
            workdir: Working directory inside the container.
            environment: Extra env vars for this exec invocation.
            detach: If ``True`` (default), return immediately with an exec-ID
                string.  If ``False``, block and return ``(exit_code, output)``.
            stream: If ``True``, return ``(exec_id, output_generator)`` where
                the generator yields ``(stdout_bytes, stderr_bytes)`` tuples.

        Returns:
            * **detach=True** — The Docker exec-ID (``str``).
            * **detach=False** — A ``(exit_code, output)`` tuple.
            * **stream=True** — A ``(exec_id, generator)`` tuple.
        """
        if not self._container:
            raise RuntimeError("Container is not running.")

        logger.info("Executing in container: %s (cwd=%s)", cmd, workdir)

        if stream:
            resp = self._client.api.exec_create(
                self._container.id, cmd,
                workdir=workdir, environment=environment,
                stdout=True, stderr=True,
            )
            eid = resp["Id"]
            output = self._client.api.exec_start(eid, stream=True, demux=True)
            return eid, output

        if detach:
            resp = self._client.api.exec_create(
                self._container.id, cmd,
                workdir=workdir, environment=environment,
                stdout=True, stderr=True,
            )
            eid = resp["Id"]
            output_gen = self._client.api.exec_start(eid, detach=False, stream=True, demux=True)
            cmd_label = os.path.basename(cmd[0]) if isinstance(cmd, list) and cmd else eid[:12]
            self._output_readers[eid] = _OutputReader(eid, output_gen, cmd_label=cmd_label)
            logger.debug("Detached exec started: %s", eid[:12])
            return eid

        # Synchronous mode
        result = self._container.exec_run(cmd, workdir=workdir, environment=environment)
        if result.output:
            for line in result.output.decode("utf-8", errors="replace").splitlines():
                logger.info("%s", line)
        return result

    def exec_inspect(self, exec_id):
        """Return the raw ``exec_inspect`` dict for *exec_id*."""
        return self._client.api.exec_inspect(exec_id)

    def is_exec_running(self, exec_id):
        """Return ``True`` if *exec_id* is still running."""
        if not exec_id:
            return False
        try:
            return self._client.api.exec_inspect(exec_id)["Running"]
        except Exception:
            return False

    def wait_exec(self, exec_id, timeout=15.0, poll_interval=0.2):
        """Block until *exec_id* finishes or *timeout* expires.

        Returns the exit code, or ``None`` on timeout.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            info = self._client.api.exec_inspect(exec_id)
            if not info["Running"]:
                reader = self._output_readers.get(exec_id)
                if reader:
                    reader.join(timeout=2.0)
                return info["ExitCode"]
            time.sleep(poll_interval)
        return None

    def get_exec_output(self, exec_id):
        """Return captured output lines for *exec_id*, or ``[]``."""
        reader = self._output_readers.get(exec_id)
        return reader.output if reader else []

    def kill_exec(self, exec_id, signal=9):
        """Kill the process behind *exec_id*.

        Tries host-side ``os.kill`` first, then falls back to scanning
        ``/proc`` inside the container.

        Returns the exit code, or ``-9`` on failure.
        """
        info = self._client.api.exec_inspect(exec_id)
        pid = info.get("Pid", 0)

        # Strategy 1: host-side os.kill
        if pid:
            try:
                os.kill(pid, signal)
            except (ProcessLookupError, PermissionError, OSError):
                pass

        exit_code = self.wait_exec(exec_id, timeout=2.0)
        if exit_code is not None:
            return exit_code

        # Strategy 2: in-container /proc cmdline match
        if self._container:
            try:
                pc = info.get("ProcessConfig", {})
                entry = pc.get("entrypoint", "")
                args = pc.get("arguments", [])
                full_cmd = " ".join([entry] + (args or [])) if entry else ""

                if full_cmd:
                    escaped = full_cmd.replace("'", "'\\''")
                    self._container.exec_run([
                        "sh", "-c",
                        f"target='{escaped} '; "
                        "for p in /proc/[0-9]*/; do "
                        "cpid=${p#/proc/}; cpid=${cpid%%/}; "
                        '[ "$cpid" = "1" ] && continue; '
                        "cmdline=$(cat /proc/$cpid/cmdline 2>/dev/null | "
                        "tr '\\0' ' ') || continue; "
                        '[ "$cmdline" = "$target" ] && '
                        f"kill -{signal} $cpid 2>/dev/null; "
                        "done",
                    ])
            except Exception:
                logger.debug("In-container kill failed", exc_info=True)

        exit_code = self.wait_exec(exec_id, timeout=5.0)
        return exit_code if exit_code is not None else -9

    # ------------------------------------------------------------------
    # Network inspection
    # ------------------------------------------------------------------

    def get_ip(self, network="bridge"):
        """Return the container's IP address on *network*."""
        self.reload()
        return self.attrs["NetworkSettings"]["Networks"][network]["IPAddress"]

    def get_gateway(self, network="bridge"):
        """Return the gateway address for *network*."""
        self.reload()
        return self.attrs["NetworkSettings"]["Networks"][network]["Gateway"]

    # ------------------------------------------------------------------
    # File transfer
    # ------------------------------------------------------------------

    def copy_to(self, host_path, container_path):
        """Copy a file/directory from the host **into** the container."""
        if not self._container:
            raise RuntimeError("Container is not running.")
        logger.info("Copying %s -> container:%s", host_path, container_path)
        tar_stream = io.BytesIO()
        with tarfile.open(fileobj=tar_stream, mode="w") as tar:
            tar.add(host_path, arcname=os.path.basename(container_path))
        tar_stream.seek(0)
        self._container.put_archive(os.path.dirname(container_path) or "/", tar_stream)

    def copy_from(self, container_path, host_path):
        """Copy a file/directory **out of** the container to the host."""
        if not self._container:
            raise RuntimeError("Container is not running.")
        logger.info("Copying container:%s -> %s", container_path, host_path)
        bits, _ = self._container.get_archive(container_path)
        tar_stream = io.BytesIO()
        for chunk in bits:
            tar_stream.write(chunk)
        tar_stream.seek(0)
        os.makedirs(os.path.dirname(host_path) or ".", exist_ok=True)
        with tarfile.open(fileobj=tar_stream) as tar:
            members = tar.getmembers()
            if len(members) == 1 and not members[0].isdir():
                f = tar.extractfile(members[0])
                if f is not None:
                    with open(host_path, "wb") as out:
                        out.write(f.read())
            else:
                tar.extractall(path=os.path.dirname(host_path) or ".")

    # ------------------------------------------------------------------
    # SSH
    # ------------------------------------------------------------------

    def ssh(self, username="score", password="score", port=2222):
        from score.itf.core.com.ssh import Ssh  # lazy import — paramiko optional
        return Ssh(target_ip=self.get_ip(), port=port, username=username, password=password)

    # ------------------------------------------------------------------
    # TcpDump
    # ------------------------------------------------------------------

    def tcpdump_handler(self):
        """Return a :class:`DockerTcpDumpHandler` bound to this target.

        Use with :class:`~score.itf.core.com.tcpdump.TcpDumpCapture`::

            from score.itf.core.com.tcpdump import TcpDumpCapture

            with TcpDumpCapture(target.tcpdump_handler(), filter_expr="icmp") as cap:
                ...
        """
        return DockerTcpDumpHandler(self)

    @property
    def raw(self):
        """The underlying ``docker.models.containers.Container``."""
        return self._container


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope=determine_target_scope)
def docker_configuration():
    """Customisation point for the Docker container.

    Override in ``conftest.py`` to set environment, volumes, shm_size, etc.

    Returns:
        dict: Configuration overrides merged into the defaults.
    """
    return {}


@pytest.fixture(scope=determine_target_scope)
def _docker_configuration(docker_configuration):
    defaults = {
        "command": "sleep infinity",
        "init": True,
        "environment": {},
    }
    return {**defaults, **docker_configuration}


@pytest.fixture(scope=determine_target_scope)
def target_init(request, _docker_configuration):
    print(_docker_configuration)

    docker_image_bootstrap = request.config.getoption("docker_image_bootstrap")
    docker_image = request.config.getoption("docker_image")

    if docker_image_bootstrap:
        logger.info("Executing bootstrap command: %s", docker_image_bootstrap)
        subprocess.run([docker_image_bootstrap], check=True)

    client = get_docker_client()

    kwargs = dict(
        command=_docker_configuration["command"],
        detach=True,
        auto_remove=True,
        init=_docker_configuration.get("init", True),
    )
    if _docker_configuration.get("environment"):
        kwargs["environment"] = _docker_configuration["environment"]
    if _docker_configuration.get("volumes"):
        kwargs["volumes"] = _docker_configuration["volumes"]
    if _docker_configuration.get("privileged"):
        kwargs["privileged"] = True
    if _docker_configuration.get("network_mode"):
        kwargs["network_mode"] = _docker_configuration["network_mode"]
    if _docker_configuration.get("shm_size"):
        kwargs["shm_size"] = _docker_configuration["shm_size"]

    logger.info("Starting container from image %s", docker_image)
    container = client.containers.run(docker_image, **kwargs)
    logger.info("Container started: %s", container.short_id)

    yield DockerTarget(client, container)

    # Teardown
    cid = container.short_id
    logger.info("Stopping container %s", cid)
    try:
        container.stop(timeout=1)
    except Exception:
        logger.debug("Container stop failed (may already be removed)", exc_info=True)
