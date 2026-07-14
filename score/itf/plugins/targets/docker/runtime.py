# *******************************************************************************
# Copyright (c) 2025-2026 Contributors to the Eclipse Foundation
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
"""Docker runtime library: container management, exec, file transfer."""

import io
import logging
import os
import shlex
import subprocess
import tarfile
import threading
import time

import docker as pypi_docker

from score.itf.core.process.async_process import AsyncProcess

logger = logging.getLogger(__name__)

# Default timeout (seconds) for Docker client operations.
DOCKER_CLIENT_TIMEOUT = 180


class DockerAsyncProcess(AsyncProcess):
    """Handle for a non-blocking command execution inside a Docker container."""

    def __init__(self, container, client, exec_id, pid, output_thread, output_lines):
        self._container = container
        self._client = client
        self.exec_id = exec_id
        self._pid = pid
        self._output_thread = output_thread
        self._output_lines = output_lines
        self._logger = logging.getLogger(f"async_exec.{pid}")

    def pid(self) -> int:
        return self._pid

    def is_running(self) -> bool:
        return self._client.api.exec_inspect(self.exec_id)["Running"]

    def get_exit_code(self) -> int:
        return self._client.api.exec_inspect(self.exec_id)["ExitCode"]

    def wait(self, timeout_s: float = 15) -> int:
        start_time = time.time()
        while self.is_running():
            if time.time() - start_time > timeout_s:
                raise RuntimeError(
                    f"Waiting for process with PID [{self._pid}] to terminate timed out after {timeout_s} seconds"
                )
            time.sleep(0.1)
        self._output_thread.join()
        return self.get_exit_code()

    def stop(self) -> int:
        self._terminate()
        for _ in range(5):
            time.sleep(1)
            if not self.is_running():
                break
        if self.is_running():
            self._logger.error(f"Process with PID [{self._pid}] did not terminate properly, sending SIGKILL.")
            self._kill()
            self.wait()
        self._output_thread.join()
        return self.get_exit_code()

    def _terminate(self):
        self._container.exec_run(["/bin/bash", "-c", f"kill {self._pid}"])

    def _kill(self):
        self._container.exec_run(["/bin/bash", "-c", f"kill -9 {self._pid}"])

    def get_output(self) -> str:
        return "\n".join(self._output_lines) + ("\n" if self._output_lines else "")


class DockerRuntime:
    """Runtime wrapper around a Docker container providing exec, upload, download."""

    def __init__(self, container, network=None):
        self.container = container
        self.network = network
        self._client = pypi_docker.from_env(timeout=DOCKER_CLIENT_TIMEOUT)

    def __getattr__(self, name):
        return getattr(self.container, name)

    def wrap_exec(self, *args, **kwargs):
        """Create a WrappedProcess for lifecycle-managed async execution."""
        from score.itf.core.process.wrapped_process import WrappedProcess

        return WrappedProcess(self, *args, **kwargs)

    def execute(self, command: str):
        return self.container.exec_run(f"/bin/sh -c {shlex.quote(command)}")

    def execute_async(self, binary_path, args=None, cwd="/", **kwargs) -> DockerAsyncProcess:
        if args is None:
            args = []
        command = f"{binary_path} {' '.join(shlex.quote(a) for a in args)}"
        exec_instance = self._client.api.exec_create(
            self.container.id,
            cmd=[
                "/bin/bash",
                "-c",
                f"echo $$; exec /bin/bash -c {shlex.quote(command)}",
            ],
            workdir=cwd,
        )
        exec_id = exec_instance["Id"]
        stream = self._client.api.exec_start(exec_id, stream=True, demux=True)

        cmd_logger = logging.getLogger(os.path.basename(command.split()[0]))
        output_lines = []

        def _process_text(text):
            for line in text.strip().split("\n"):
                if line:
                    cmd_logger.info(line)
                    output_lines.append(line)

        pid = None
        for stdout_chunk, stderr_chunk in stream:
            if stderr_chunk:
                _process_text(stderr_chunk.decode())
            if stdout_chunk:
                pid_line, _, remainder = stdout_chunk.decode().partition("\n")
                pid = int(pid_line.strip())
                if remainder.strip():
                    _process_text(remainder)
                break

        if pid is None:
            raise RuntimeError(f"Failed to extract PID from stdout for '{command}'")

        def _async_log(log_stream):
            for stdout_chunk, stderr_chunk in log_stream:
                if stdout_chunk:
                    _process_text(stdout_chunk.decode())
                if stderr_chunk:
                    _process_text(stderr_chunk.decode())

        output_thread = threading.Thread(target=_async_log, args=(stream,), daemon=True)
        output_thread.start()

        return DockerAsyncProcess(self.container, self._client, exec_id, pid, output_thread, output_lines)

    def upload(self, local_path: str, remote_path: str) -> None:
        if not os.path.isfile(local_path):
            raise FileNotFoundError(local_path)

        remote_dir = os.path.dirname(remote_path) or "/"
        remote_name = os.path.basename(remote_path)

        tar_stream = io.BytesIO()
        with tarfile.open(fileobj=tar_stream, mode="w", dereference=True) as tar:
            tar.add(local_path, arcname=remote_name)
        tar_stream.seek(0)

        ok = self.container.put_archive(remote_dir, tar_stream.getvalue())
        if not ok:
            raise RuntimeError(f"Failed to upload '{local_path}' to '{remote_path}'")

    def download(self, remote_path: str, local_path: str) -> None:
        stream, _ = self.container.get_archive(remote_path)
        tar_bytes = b"".join(stream)

        os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:*") as tar:
            members = tar.getmembers()
            if not members:
                raise FileNotFoundError(remote_path)

            member = members[0]
            extracted = tar.extractfile(member)
            if extracted is None:
                raise FileNotFoundError(remote_path)
            with open(local_path, "wb") as f:
                f.write(extracted.read())

    def restart(self) -> None:
        self.container.restart()

    def _network_attr(self, key, network=None):
        if network is None and self.network is not None:
            network = self.network.name
        self.container.reload()
        networks = self.container.attrs["NetworkSettings"]["Networks"]
        if network is not None:
            if network not in networks:
                raise RuntimeError(f"Container {self.container.short_id} is not attached to network '{network}'")
            return networks[network][key]
        value = next(
            (v.get(key) for v in networks.values() if v.get(key, "") != ""),
            None,
        )
        if value is None:
            raise RuntimeError(f"Container {self.container.short_id} has no {key} on any network")
        return value

    def get_ip(self, network=None):
        return self._network_attr("IPAddress", network)

    def get_gateway(self, network=None):
        return self._network_attr("Gateway", network)


class DockerExecInterface:
    """Narrow adapter exposing only execution-related methods.

    This is returned for the ``itf/cap/exec`` contract so callers cannot
    accidentally depend on unrelated target methods (upload/download/restart).
    """

    def __init__(self, runtime: DockerRuntime):
        self._runtime = runtime

    def execute(self, command: str):
        return self._runtime.execute(command)

    def execute_async(self, binary_path, args=None, cwd="/", **kwargs):
        return self._runtime.execute_async(binary_path, args=args, cwd=cwd, **kwargs)

    def wrap_exec(self, *args, **kwargs):
        return self._runtime.wrap_exec(*args, **kwargs)


def extract_coverage_from_container(target, output_base):
    """Extract .gcda coverage files created inside the container."""
    diff = target.container.diff()
    if not diff:
        return
    gcda_paths = [entry["Path"] for entry in diff if entry["Path"].endswith(".gcda") and entry["Kind"] in (0, 1)]
    for remote_path in gcda_paths:
        local_path = os.path.join(output_base, remote_path.lstrip("/"))
        if not os.path.realpath(local_path).startswith(os.path.realpath(output_base)):
            logger.warning(f"Skipping path traversal attempt: {remote_path}")
            continue
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        try:
            target.download(remote_path, local_path)
        except Exception:
            logger.warning(f"Failed to extract {remote_path}", exc_info=True)


def docker_target_runtime(docker_image: str, merged_configuration: dict):
    """Generator that creates and yields a DockerRuntime, cleaning up on exit."""
    docker_image_bootstrap = merged_configuration.get("bootstrap_command")
    if docker_image_bootstrap:
        logger.info(f"Executing custom image bootstrap command: {docker_image_bootstrap}")
        result = subprocess.run([docker_image_bootstrap], capture_output=True, text=True)
        if result.stdout:
            logger.info(f"Bootstrap stdout: {result.stdout}")
        if result.stderr:
            logger.error(f"Bootstrap stderr: {result.stderr}")
        if result.returncode != 0:
            logger.error(f"Bootstrap failed with exit code {result.returncode}")
            raise subprocess.CalledProcessError(result.returncode, docker_image_bootstrap)

    client = pypi_docker.from_env(timeout=DOCKER_CLIENT_TIMEOUT)

    known_keys = {
        "command",
        "init",
        "environment",
        "volumes",
        "shm_size",
        "detach",
        "auto_remove",
        "bootstrap_command",
        "extract_coverage",
        "coverage_output_dir",
    }
    reserved_overrides = {k for k in ("detach", "auto_remove") if k in merged_configuration}
    if reserved_overrides:
        logger.warning(f"docker_configuration contains reserved keys {reserved_overrides} which will be ignored")
    extra_kwargs = {k: v for k, v in merged_configuration.items() if k not in known_keys}

    network = client.networks.create(
        f"score_itf_{os.urandom(8).hex()}",
        driver="bridge",
    )

    try:
        container = client.containers.run(
            docker_image,
            merged_configuration["command"],
            detach=True,
            auto_remove=False,
            init=merged_configuration["init"],
            environment=merged_configuration["environment"],
            volumes=merged_configuration["volumes"],
            shm_size=merged_configuration["shm_size"],
            network=network.name,
            **extra_kwargs,
        )
    except Exception:
        network.remove()
        raise

    target = None
    try:
        target = DockerRuntime(container, network=network)
        yield target
    finally:
        try:
            if target is not None and merged_configuration.get("extract_coverage"):
                extract_coverage_from_container(
                    target,
                    merged_configuration.get("coverage_output_dir", "/tmp/sysroot"),
                )
        except Exception:
            logger.warning("Coverage extraction failed", exc_info=True)
        try:
            try:
                container.stop(timeout=1)
            finally:
                container.remove(force=True)
        finally:
            try:
                network.remove()
            except Exception:
                logger.warning(f"Failed to remove network {network.name}", exc_info=True)
