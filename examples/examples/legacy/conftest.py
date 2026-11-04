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
"""Legacy facade: ITF's original command-line options, fixtures and target API, served by ITF packs.
ITF's part (readiness, evidence) is the policy beside the target files (targets/policy.py).

Declarative half: the target file the options select (targets/docker*.itf.yaml for --docker-image,
targets/qemu*.itf.yaml for --qemu-config; the *_dlt variants when DLT options are given),
parameterised through the environment. Code half: the original fixtures (`target`,
`docker_configuration`, `dlt_config`, `dlt`), returning adapters over the target file's roles.
`dlt_on_target` comes from the dlt pack itself. The container is renewed per test unless
--keep-target, as the original plugin did.
"""

import json
import logging
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from legacy_itf import dlt as legacy_dlt
from legacy_itf.docker import DockerTarget
from legacy_itf.qemu import QemuTarget
from legacy_itf.target import UnsupportedTarget

logger = logging.getLogger(__name__)

TARGET_FILES = Path(__file__).with_name("targets")
_policy: dict = {}


def pytest_addoption(parser):
    group = parser.getgroup("legacy itf")
    group.addoption("--docker-image", help="Docker image to run tests against.")
    group.addoption("--docker-image-bootstrap", help="Command run before the image is referenced (e.g. oci_load).")
    group.addoption(
        "--extract-coverage",
        action="store_true",
        default=False,
        help="Extract coverage files (.gcda) from the container before teardown.",
    )
    group.addoption("--coverage-output-dir", default=None, help="Where extracted coverage files go.")
    group.addoption("--qemu-config", help="Path to json file with target configurations.")
    group.addoption("--qemu-kernel", help="Path to a QEMU kernel image.")
    group.addoption("--qemu-image", help="[DEPRECATED] Alias for --qemu-kernel.")
    group.addoption("--qemu-rootfs", help="Path to a QEMU disk image, booted through a temporary overlay.")
    group.addoption("--qemu-disk", help="Path to an additional disk image.")
    group.addoption("--dlt-config", help="Path to json file with dlt configurations.")
    group.addoption("--dlt-receive-path", help="Accepted for compatibility: the dlt pack ships dlt-receive.")
    group.addoption("--keep-target", action="store_true", help="Keep the container between tests.")


def _dlt_settings(config) -> dict:
    path = config.getoption("dlt_config")
    settings = json.loads(Path(path).read_text(encoding="utf-8")) if path else {}
    return {
        "host_ip": settings.get("host_ip", "127.0.0.1"),
        "target_ip": settings.get("target_ip", "127.0.0.1"),
        "multicast_ips": settings.get("multicast_ips", []),
    }


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    """Translate the original options into a target file (`--itf-target`) and its environment."""
    option = config.getoption
    with_dlt = bool(option("dlt_receive_path") or option("dlt_config"))
    if option("docker_image"):
        _policy["kind"] = "docker"
        settings = {
            "LEGACY_DOCKER_IMAGE": option("docker_image"),
            "LEGACY_DOCKER_BOOTSTRAP": option("docker_image_bootstrap"),
            "LEGACY_EXTRACT_COVERAGE": "true" if option("extract_coverage") else "false",
            "LEGACY_COVERAGE_DIR": option("coverage_output_dir"),
            # the original plugin's fixed login for its SSH image, unless the environment gives another
            "LEGACY_SSH_USER": os.environ.get("LEGACY_SSH_USER", "score"),
            "LEGACY_SSH_PASSWORD": os.environ.get("LEGACY_SSH_PASSWORD", "score"),
        }
    elif option("qemu_config"):
        _policy["kind"] = "qemu"
        paths = {
            "LEGACY_QEMU_CONFIG": option("qemu_config"),
            "LEGACY_QEMU_KERNEL": option("qemu_kernel") or option("qemu_image"),
            "LEGACY_QEMU_ROOTFS": option("qemu_rootfs"),
            "LEGACY_QEMU_DISK": option("qemu_disk"),
        }
        settings = {k: os.path.abspath(v) for k, v in paths.items() if v}
    else:
        return
    _policy["target_file"] = TARGET_FILES / f"{_policy['kind']}{'_dlt' if with_dlt else ''}.itf.yaml"
    if with_dlt:
        dlt = _dlt_settings(config)
        settings |= {"LEGACY_DLT_HOST_IP": dlt["host_ip"], "LEGACY_DLT_MULTICAST": ",".join(dlt["multicast_ips"])}
    os.environ.update({k: v for k, v in settings.items() if v is not None})
    config.option.itf_target = str(_policy["target_file"])  # the same as `pytest --itf-target ...`


@pytest.fixture(autouse=True)
def _narrate(request):
    """One INFO line per scenario, so the log reads as a story (details stay at DEBUG)."""
    logger.info("scenario: %s", request.node.name.removeprefix("test_").replace("_", " "))
    yield


def pytest_runtest_logreport(report):
    if report.when == "call" or report.outcome == "skipped":
        logger.info("verdict: %s %s", report.nodeid.split("::")[-1], report.outcome)


@pytest.fixture(scope="session", autouse=True)
def _legacy_dlt_session(session):
    if session is not None:
        legacy_dlt.bind(session)


@pytest.fixture(scope="session")
def docker_configuration():
    """Override to customize the container: environment, command, init, shm_size, volumes."""
    return {}


_applied: dict = {}


@pytest.fixture
def target(request, docker_configuration):
    kind = _policy.get("kind")
    if kind is None:
        yield UnsupportedTarget()
        return
    session = request.getfixturevalue("session")
    if kind == "qemu":
        request.getfixturevalue("dlt")
        yield QemuTarget(session.target)
        return
    configuration = dict(docker_configuration)
    platform = session.target.platform
    # The original plugin gave each test a fresh container unless --keep-target was set.
    keep = request.config.getoption("keep_target")
    if platform.running() and (not keep or _applied.get("configuration") != configuration):
        session.discard("platform")  # a fresh platform the settings below apply to, started by the reach
        platform = session.target.platform
    if not platform.running():
        for key, value in configuration.items():
            if key in {"environment", "command", "init", "shm_size", "volumes", "privileged"}:
                setattr(platform, key, value)
            else:
                logger.warning("docker_configuration key %r is not supported and is ignored", key)
        session.reach("platform.up")
        _applied["configuration"] = configuration
    yield DockerTarget(session.target)


@pytest.fixture(scope="session")
def dlt_config(request):
    return SimpleNamespace(
        **_dlt_settings(request.config), dlt_receive_path=request.config.getoption("dlt_receive_path") or "dlt-receive"
    )


@pytest.fixture(scope="session")
def dlt(session):
    """Records DLT for the session when the target file has a logs role (QEMU targets request it)."""
    if session is None or not session.target.has("logs"):
        yield
        return
    session.reach("logs.active")  # the target file's logs role records for the session
    yield
