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
"""Legacy infra policy: ITF's original command-line options, fixtures and target API, served by
ITF packs.

Declarative half: the recipe the options select (recipes/docker*.yaml for --docker-image,
recipes/qemu*.yaml for --qemu-config; the *_dlt variants when DLT options are given),
parameterised through the environment. Code half: the original fixtures (`target`,
`docker_configuration`, `dlt_config`, `dlt`), returning adapters over the recipe's nodes.
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
from score.itf.core import hookimpl, load_init, load_setup

logger = logging.getLogger(__name__)

COMMAND = "itf.capabilities.exec.command"
CONSOLE = "itf.capabilities.exec.console"
EVIDENCE = Path(os.environ.get("TEST_UNDECLARED_OUTPUTS_DIR", ".")) / "evidence"
RECIPES = Path(__file__).with_name("recipes")
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
    """Translate the original options into a recipe and its environment."""
    option = config.getoption
    with_dlt = bool(option("dlt_receive_path") or option("dlt_config"))
    if option("docker_image"):
        _policy["kind"] = "docker"
        settings = {
            "LEGACY_DOCKER_IMAGE": option("docker_image"),
            "LEGACY_DOCKER_BOOTSTRAP": option("docker_image_bootstrap"),
            "LEGACY_EXTRACT_COVERAGE": "true" if option("extract_coverage") else "false",
            "LEGACY_COVERAGE_DIR": option("coverage_output_dir"),
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
    _policy["recipe"] = RECIPES / f"{_policy['kind']}{'_dlt' if with_dlt else ''}.yaml"
    if with_dlt:
        dlt = _dlt_settings(config)
        settings |= {"LEGACY_DLT_HOST_IP": dlt["host_ip"], "LEGACY_DLT_MULTICAST": ",".join(dlt["multicast_ips"])}
    os.environ.update({k: v for k, v in settings.items() if v is not None})


@hookimpl
def itf_setup(ctx):
    if "recipe" in _policy:
        load_setup(ctx, _policy["recipe"])


@hookimpl
def itf_init(ctx):
    if "recipe" in _policy:
        load_init(ctx, _policy["recipe"])


@hookimpl
def itf_verify(session):
    """Nothing to check yet for a docker recipe: the container is started per test by the `target` fixture
    (as the original plugin did), so only what the session itself has up is verified."""
    target = session.target
    logger.info("verify: target offers %s", ", ".join(sorted(target.tokens())))
    if target.has("itf.capabilities.platform.instance") and target.platform.running() and target.has(COMMAND):
        code, output = target.command.exec("echo -n ready")
        session.check("command.answers", code == 0 and output.strip().endswith("ready"), detail=f"exit {code}")


@hookimpl
def itf_teardown(session):
    """Evidence, collected while the target still runs: console transcript and container output."""
    target = session.target
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    if target.has(CONSOLE):
        path = EVIDENCE / "console.txt"
        path.write_text("\n".join(target.console.lines()), encoding="utf-8")
        logger.info("teardown: console transcript (%d lines) saved to %s", len(target.console.lines()), path)
    container = (
        getattr(target.platform, "container", None) if target.has("itf.capabilities.platform.instance") else None
    )
    if container is not None:
        path = EVIDENCE / "container.log"
        path.write_bytes(container.logs())
        logger.info("teardown: container output saved to %s", path)


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
        session.renew("platform")
        platform = session.target.platform
    if not platform.running():
        for key, value in configuration.items():
            if key in {"environment", "command", "init", "shm_size", "volumes", "privileged"}:
                setattr(platform, key, value)
            else:
                logger.warning("docker_configuration key %r is not supported and is ignored", key)
        session.reach("itf.states.platform.up")
        _applied["configuration"] = configuration
    yield DockerTarget(session.target)


@pytest.fixture(scope="session")
def dlt_config(request):
    return SimpleNamespace(
        **_dlt_settings(request.config), dlt_receive_path=request.config.getoption("dlt_receive_path") or "dlt-receive"
    )


@pytest.fixture(scope="session")
def dlt(session):
    """Records DLT for the session when the recipe has a logs node (QEMU targets request it)."""
    if session is None or not session.target.has(legacy_dlt.LOGS):
        yield
        return
    session.reach("itf.states.logs.active")  # the recipe's logs node records for the session
    yield
