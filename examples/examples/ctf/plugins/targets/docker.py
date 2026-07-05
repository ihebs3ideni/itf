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
"""Docker TARGET: assemble a container and publish capability contracts.

Publishes the shared, target-agnostic capabilities backed by a running
container:

    ctf/cap/exec           execute(cmd) -> (code, bytes)
    ctf/cap/file_transfer  upload() / download()
    ctf/cap/restart        restart()
    ctf/cap/network        ip() / gateway()      (docker-specific)

The container is configurable from a level's conftest/ini via CLI options
(``--ctf-docker-image``, ``--ctf-docker-mount``, ``--ctf-docker-publish``), so
the same target plugin serves both the target-agnostic integration level and
the docker-specific level. Depends only on the ``docker`` SDK and ``ctf``.
"""

from __future__ import annotations

import io
import os
import shlex
import tarfile

import docker as pypi_docker

from ctf.contracts import provides, requires
from ctf.descriptor import Descriptor
from ctf.target import TARGET_ANCHOR

from plugins.capabilities import exec as cap_exec
from plugins.capabilities import file_transfer as cap_file_transfer
from plugins.capabilities import network as cap_network
from plugins.capabilities import restart as cap_restart

#: Timeout (seconds) for Docker client operations.
DOCKER_CLIENT_TIMEOUT = 180

#: Default image; overridable with ``--ctf-docker-image``.
DEFAULT_IMAGE = "ubuntu:24.04"


# --------------------------------------------------------------------------
# Internal backing handle: a running container. Not a public contract.
# --------------------------------------------------------------------------
class _Container:
    def __init__(self, container, network=None):
        self.container = container
        self.network = network

    def exec_run(self, command: str):
        return self.container.exec_run(f"/bin/sh -c {shlex.quote(command)}")

    def network_attr(self, key: str):
        self.container.reload()
        networks = self.container.attrs["NetworkSettings"]["Networks"]
        if self.network is not None and self.network.name in networks:
            return networks[self.network.name][key]
        value = next((v.get(key) for v in networks.values() if v.get(key)), None)
        if value is None:
            raise RuntimeError(f"container has no {key} on any network")
        return value


# --------------------------------------------------------------------------
# Capability adapters -- each matches the Protocol in the matching capability
# module. An SSH/QEMU target would provide equivalents under the same contracts.
# --------------------------------------------------------------------------
class _Exec:
    def __init__(self, backend: _Container):
        self._backend = backend

    def execute(self, command: str) -> tuple[int, bytes]:
        return self._backend.exec_run(command)


class _FileTransfer:
    def __init__(self, backend: _Container):
        self._backend = backend

    def upload(self, local_path: str, remote_path: str) -> None:
        if not os.path.isfile(local_path):
            raise FileNotFoundError(local_path)
        remote_dir = os.path.dirname(remote_path) or "/"
        remote_name = os.path.basename(remote_path)

        tar_stream = io.BytesIO()
        with tarfile.open(fileobj=tar_stream, mode="w", dereference=True) as tar:
            tar.add(local_path, arcname=remote_name)
        tar_stream.seek(0)

        ok = self._backend.container.put_archive(remote_dir, tar_stream.getvalue())
        if not ok:
            raise RuntimeError(f"Failed to upload '{local_path}' to '{remote_path}'")

    def download(self, remote_path: str, local_path: str) -> None:
        stream, _ = self._backend.container.get_archive(remote_path)
        tar_bytes = b"".join(stream)
        os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:*") as tar:
            members = tar.getmembers()
            if not members:
                raise FileNotFoundError(remote_path)
            extracted = tar.extractfile(members[0])
            if extracted is None:
                raise FileNotFoundError(remote_path)
            with open(local_path, "wb") as f:
                f.write(extracted.read())


class _Restart:
    def __init__(self, backend: _Container):
        self._backend = backend

    def restart(self) -> None:
        self._backend.container.restart()


class _Network:
    def __init__(self, backend: _Container):
        self._backend = backend

    def ip(self) -> str:
        return self._backend.network_attr("IPAddress")

    def gateway(self) -> str:
        return self._backend.network_attr("Gateway")


# --------------------------------------------------------------------------
# Provider: bring a container up lazily, tear it down at session scope exit.
# --------------------------------------------------------------------------
@provides(TARGET_ANCHOR)
@requires("docker/image", "docker/config")
def docker_container(image: str, config: dict):
    # The acquired target handle: the generic ``ctf/target`` anchor rooting the
    # mandatory bring-up spine. Capabilities attach above it.
    client = pypi_docker.from_env(timeout=DOCKER_CLIENT_TIMEOUT)

    network = client.networks.create(f"ctf_docker_{os.urandom(8).hex()}", driver="bridge")

    known = {"command", "init", "environment", "volumes", "shm_size"}
    extra = {k: v for k, v in config.items() if k not in known}
    try:
        container = client.containers.run(
            image,
            config["command"],
            detach=True,
            auto_remove=False,
            init=config["init"],
            environment=config["environment"],
            volumes=config["volumes"],
            shm_size=config["shm_size"],
            network=network.name,
            **extra,
        )
    except Exception:
        network.remove()
        raise

    backend = _Container(container, network=network)
    try:
        yield backend
    finally:
        try:
            container.stop(timeout=1)
        finally:
            container.remove(force=True)
        try:
            network.remove()
        except Exception:
            pass


# --------------------------------------------------------------------------
# Capability providers: publish the shared contracts backed by the container.
# --------------------------------------------------------------------------
@provides(cap_exec.CONTRACT)
@requires(TARGET_ANCHOR)
def exec_capability(backend: _Container) -> cap_exec.Exec:
    return _Exec(backend)


@provides(cap_file_transfer.CONTRACT)
@requires(TARGET_ANCHOR)
def file_transfer_capability(backend: _Container) -> cap_file_transfer.FileTransfer:
    return _FileTransfer(backend)


@provides(cap_restart.CONTRACT)
@requires(TARGET_ANCHOR)
def restart_capability(backend: _Container) -> cap_restart.Restart:
    return _Restart(backend)


@provides(cap_network.CONTRACT)
@requires(TARGET_ANCHOR)
def network_capability(backend: _Container) -> cap_network.Network:
    return _Network(backend)


# --------------------------------------------------------------------------
# Contribution hooks
# --------------------------------------------------------------------------
def pytest_addoption(parser):
    group = parser.getgroup("ctf-docker")
    group.addoption(
        "--ctf-docker-image",
        action="store",
        default=DEFAULT_IMAGE,
        help="Docker image the CTF docker target runs against.",
    )
    group.addoption(
        "--ctf-docker-mount",
        action="append",
        default=[],
        metavar="HOSTPATH:CONTAINERPATH",
        help="Bind-mount a host path into the container (repeatable).",
    )
    group.addoption(
        "--ctf-docker-publish",
        action="append",
        default=[],
        metavar="CONTAINERPORT",
        help="Publish a container TCP port to a random host port (repeatable).",
    )


def _volumes(mounts: list[str]) -> dict:
    volumes: dict = {}
    for spec in mounts:
        host, _, container = spec.partition(":")
        if not host or not container:
            raise ValueError(f"--ctf-docker-mount must be HOSTPATH:CONTAINERPATH, got {spec!r}")
        volumes[os.path.abspath(host)] = {"bind": container, "mode": "rw"}
    return volumes


def _ports(publish: list[str]) -> dict:
    return {f"{port}/tcp": None for port in publish}


def _opt(config, name, default):
    """Read a CLI option, tolerating targets registered after option parsing."""
    if config is None:
        return default
    try:
        value = config.getoption(name)
    except (ValueError, KeyError):
        return default
    return default if value is None else value


def pytest_ctf_setup(registry, config):
    image = _opt(config, "--ctf-docker-image", DEFAULT_IMAGE)
    mounts = _opt(config, "--ctf-docker-mount", [])
    publish = _opt(config, "--ctf-docker-publish", [])

    docker_config = {
        "command": "sleep infinity",
        "init": True,
        "environment": {},
        "shm_size": "2G",
        "volumes": _volumes(mounts),
    }
    ports = _ports(publish)
    if ports:
        docker_config["ports"] = ports

    registry.add_descriptor(Descriptor("docker/image", value=image))
    registry.add_descriptor(Descriptor("docker/config", value=docker_config))
    registry.register(docker_container)
    registry.register(exec_capability)
    registry.register(file_transfer_capability)
    registry.register(restart_capability)
    registry.register(network_capability)
