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
"""DockerTarget — ITF target backed by a Docker container.

Also exports:

- :func:`get_docker_client` — factory with SDK compatibility patch.
"""

import io
import logging
import os
import tarfile
import time

from score.itf.plugins.core import Target
from score.itf.plugins.docker.output_reader import OutputReader
from score.itf.plugins.docker.tcpdump_handler import (
    InternalTcpDumpHandler,
    ExternalTcpDumpHandler,
    can_capture_on_host,
)

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
# DockerTarget
# ---------------------------------------------------------------------------

DOCKER_CAPABILITIES = ["exec", "tcpdump"]


def _compute_capabilities(tcpdump_bin: str = ""):
    """Compute available Docker target capabilities.

    Base capabilities are always available. ``tcpdump_external`` is only
    added if the hermetic tcpdump can capture on host interfaces.

    :param tcpdump_bin: Path to the hermetic tcpdump binary.
    """
    caps = list(DOCKER_CAPABILITIES)
    if tcpdump_bin and can_capture_on_host(tcpdump_bin):
        caps.append("tcpdump_external")
    return caps


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

    def __init__(self, client, container, tcpdump_bin: str = ""):
        """Initialize a DockerTarget.

        :param client: The Docker client.
        :param container: The Docker container.
        :param tcpdump_bin: Path to the hermetic tcpdump binary (optional).
        """
        capabilities = _compute_capabilities(tcpdump_bin)
        super().__init__(capabilities=capabilities)
        self._client = client
        self._container = container
        self._tcpdump_bin = tcpdump_bin
        self._output_readers: dict[str, OutputReader] = {}

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
        """Stop (and auto-remove if configured) the container.

        :param timeout: Seconds to wait for the container to stop gracefully.
        """
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

        :param cmd: Command as a list of strings (or a single string).
        :param workdir: Working directory inside the container.
        :param environment: Extra env vars for this exec invocation.
        :param detach: If ``True`` (default), return immediately with an exec-ID
            string.  If ``False``, block and return ``(exit_code, output)``.
        :param stream: If ``True``, return ``(exec_id, output_generator)`` where
            the generator yields ``(stdout_bytes, stderr_bytes)`` tuples.
        :returns:
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
            self._output_readers[eid] = OutputReader(eid, output_gen, cmd_label=cmd_label)
            logger.debug("Detached exec started: %s", eid[:12])
            return eid

        # Synchronous mode
        result = self._container.exec_run(cmd, workdir=workdir, environment=environment)
        if result.output:
            for line in result.output.decode("utf-8", errors="replace").splitlines():
                logger.info("%s", line)
        return result

    def exec_inspect(self, exec_id):
        """Return the raw ``exec_inspect`` dict for *exec_id*.

        :param exec_id: The Docker exec ID.
        :returns: The exec inspect dictionary.
        :rtype: dict
        """
        return self._client.api.exec_inspect(exec_id)

    def is_exec_running(self, exec_id):
        """Return ``True`` if *exec_id* is still running.

        :param exec_id: The Docker exec ID.
        :returns: Whether the exec is still running.
        :rtype: bool
        """
        if not exec_id:
            return False
        try:
            return self._client.api.exec_inspect(exec_id)["Running"]
        except Exception:
            return False

    def wait_exec(self, exec_id, timeout=15.0, poll_interval=0.2):
        """Block until *exec_id* finishes or *timeout* expires.

        :param exec_id: The Docker exec ID to wait for.
        :param timeout: Maximum seconds to wait.
        :param poll_interval: Seconds between status checks.
        :returns: The exit code, or ``None`` on timeout.
        :rtype: int or None
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
        """Return captured output lines for *exec_id*, or ``[]``.

        :param exec_id: The Docker exec ID.
        :returns: List of captured output lines.
        :rtype: list[str]
        """
        reader = self._output_readers.get(exec_id)
        return reader.output if reader else []

    def kill_exec(self, exec_id, signal=9):
        """Kill the process behind *exec_id*.

        Tries host-side ``os.kill`` first, then falls back to scanning
        ``/proc`` inside the container.

        :param exec_id: The Docker exec ID to kill.
        :param signal: Signal number to send (default 9 = SIGKILL).
        :returns: The exit code, or ``-9`` on failure.
        :rtype: int
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
        """Return the container's IP address on *network*.

        :param network: Docker network name.
        :returns: The container's IP address.
        :rtype: str
        """
        self.reload()
        return self.attrs["NetworkSettings"]["Networks"][network]["IPAddress"]

    def get_gateway(self, network="bridge"):
        """Return the gateway address for *network*.

        :param network: Docker network name.
        :returns: The gateway IP address.
        :rtype: str
        """
        self.reload()
        return self.attrs["NetworkSettings"]["Networks"][network]["Gateway"]

    # ------------------------------------------------------------------
    # File transfer
    # ------------------------------------------------------------------

    def copy_to(self, host_path, container_path):
        """Copy a file/directory from the host **into** the container.

        :param host_path: Path on the host to copy from.
        :param container_path: Path inside the container to copy to.
        """
        if not self._container:
            raise RuntimeError("Container is not running.")
        logger.info("Copying %s -> container:%s", host_path, container_path)
        tar_stream = io.BytesIO()
        with tarfile.open(fileobj=tar_stream, mode="w") as tar:
            tar.add(host_path, arcname=os.path.basename(container_path))
        tar_stream.seek(0)
        self._container.put_archive(os.path.dirname(container_path) or "/", tar_stream)

    def copy_from(self, container_path, host_path):
        """Copy a file/directory **out of** the container to the host.

        :param container_path: Path inside the container to copy from.
        :param host_path: Path on the host to copy to.
        """
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
        """Create an SSH connection to the container.

        :param username: SSH username.
        :param password: SSH password.
        :param port: SSH port inside the container.
        :returns: An :class:`~score.itf.core.com.ssh.Ssh` connection.
        """
        from score.itf.core.com.ssh import Ssh  # lazy import — paramiko optional
        return Ssh(target_ip=self.get_ip(), port=port, username=username, password=password)

    # ------------------------------------------------------------------
    # TcpDump
    # ------------------------------------------------------------------

    def internal_tcpdump_handler(self):
        """Return a handler that captures traffic **inside** the container.

        Captures loopback (127.0.0.1) traffic, internal IPC, Unix sockets, etc.
        Requires tcpdump installed in the container image.

        Use with :class:`~score.itf.core.com.tcpdump.TcpDumpCapture`::

            from score.itf.core.com.tcpdump import TcpDumpCapture

            with TcpDumpCapture(target.internal_tcpdump_handler()) as cap:
                target.exec(["curl", "http://127.0.0.1:8080"], detach=False)

        :returns: An internal tcpdump handler.
        :rtype: InternalTcpDumpHandler
        :raises RuntimeError: If the target lacks the ``tcpdump`` capability.
        """
        if not self.has_capability("tcpdump"):
            raise RuntimeError(
                "Target does not have the 'tcpdump' capability. "
                "Cannot create a tcpdump handler."
            )
        return InternalTcpDumpHandler(self)

    def external_tcpdump_handler(self):
        """Return a handler that captures traffic on the host's veth interface.

        Captures traffic entering/leaving the container (container ↔ external).
        Does NOT see loopback or internal container traffic.
        Does NOT require tcpdump in the container (uses hermetic host binary).

        Use with :class:`~score.itf.core.com.tcpdump.TcpDumpCapture`::

            from score.itf.core.com.tcpdump import TcpDumpCapture

            @requires_capabilities("tcpdump_external")
            def test_external_traffic(target):
                with TcpDumpCapture(target.external_tcpdump_handler()) as cap:
                    target.exec(["curl", "http://example.com"], detach=False)

        :returns: An external tcpdump handler.
        :rtype: ExternalTcpDumpHandler
        :raises RuntimeError: If the target lacks the ``tcpdump`` capability.
        """
        if not self.has_capability("tcpdump"):
            raise RuntimeError(
                "Target does not have the 'tcpdump' capability. "
                "Cannot create a tcpdump handler."
            )
        return ExternalTcpDumpHandler(self, self._tcpdump_bin)

    @property
    def raw(self):
        """The underlying ``docker.models.containers.Container``."""
        return self._container
