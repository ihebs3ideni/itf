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
"""Common fixtures used across whole framework"""

import fnmatch
import os
import shutil
import stat
import tarfile
import logging
import binascii
import collections
import pathlib
import pytest

import score.sctf.config as sctf_config
from score.sctf.exception import SctfRuntimeError
from score.sctf.sandbox import BwrapSandbox
from score.sctf.utils import get_filesystem_scope, list_files
from score.itf.core.utils.bunch import Bunch
from score.itf.core.utils.bazel import get_output_dir


logger = logging.getLogger(__name__)


# Pylint doesn't handle pytest fixture chains well
# pylint: disable=redefined-outer-name


@pytest.fixture(scope="session")
def bazel_solibs():
    working_dir = pathlib.Path.cwd()
    Bind = collections.namedtuple("Bind", ["src", "dst"])
    # '_solib' directory containing linkable libraries
    # Name may change with future toolchain/platform updates
    solib_dir = working_dir / "_solib_x86_64"
    if not solib_dir.is_dir():
        logger.warning(f"Directory containing hermetic shared libraries not found: '{solib_dir}'")
        return Bind(src=None, dst=None)

    # Copy '_solib' directory to resolve symlinks
    resolved_solib_dir = working_dir / "_bazel_solibs"
    if resolved_solib_dir.is_dir():
        shutil.rmtree(resolved_solib_dir)

    shutil.copytree(solib_dir, resolved_solib_dir)
    # Find all subdirs to be added to LD_LIBRARY_PATH via env var
    # Paths are constructed relative to the bwrap mount point
    bwrap_solib_dir = pathlib.Path("/usr/bazel/lib")
    lib_dirs = [
        str(bwrap_solib_dir / lib_dir.relative_to(solib_dir)) for lib_dir in solib_dir.iterdir() if lib_dir.is_dir()
    ]
    os.environ["SOLIBS_PATH"] = ":".join(lib_dirs)

    return Bind(src=resolved_solib_dir, dst=bwrap_solib_dir)


def root_dir_impl():
    """Creates a new root directory used as the root for mounted directories.

    Regular pytest 'tmpdir' fixture cannot be used due to path length limitation for UNIX sockets.
    """
    root_dir = pathlib.Path(f"/tmp/{binascii.hexlify(os.urandom(16)).decode('ascii')}")
    root_dir.mkdir()
    return root_dir


@pytest.fixture(scope=get_filesystem_scope)
def root_dir():
    return root_dir_impl()


def tmp_sysroot_impl(root_dir):
    """Creates sysroot directory inside temporary directory.

    sysroot directory contains extracted packages found in the cwd
    """
    sysroot_dir = root_dir

    matches_tar = []
    matches_tar_gz = []
    for root, dirs, filenames in os.walk(os.getcwd()):
        # Do not scan external dependencies containing locale files
        if root == os.path.join(os.getcwd(), "external"):
            dirs[:] = [d for d in dirs if d not in {"python_dateutil_default"}]

        for filename in fnmatch.filter(filenames, "*.tar"):
            matches_tar.append(os.path.join(root, filename))

        for filename in fnmatch.filter(filenames, "*.tar.gz"):
            matches_tar_gz.append(os.path.join(root, filename))

    for f in matches_tar:
        with tarfile.TarFile(f) as tar_file:
            tar_file.extractall(path=str(sysroot_dir))

    for f in matches_tar_gz:
        with tarfile.open(f, mode="r:gz") as tar_file:
            tar_file.extractall(path=str(sysroot_dir))

    for dirpath, _, filenames in os.walk(f"{str(sysroot_dir)}/opt"):
        if dirpath.endswith("bin"):
            for binary in filenames:
                os.chmod(f"{dirpath}/{binary}", stat.S_IRUSR | stat.S_IXUSR)

    return sysroot_dir


@pytest.fixture(scope=get_filesystem_scope)
def tmp_workspace():
    """Creates a temporary directory.

    The temporary directory is where all environment-specific entities are held for a particular
    test run.
    """
    # Hard-coded location for UNIX sockets (SomeIPD, ExecMgr, ...), unlikely that it can be changed
    return "/tmp"


def tmp_shm_impl(root_dir):
    """Creates temporary directory in the shared memory.

    Shared memory is separated for each test run, allowing parallel run of test.
    Shared memory can be then shared between processes executed in the same test run.
    """
    shm_dir = f"{root_dir}/dev/shm"
    os.makedirs(shm_dir)
    return shm_dir


def tmp_persistent_impl(tmp_sysroot):
    """Creates persistent dirs required by used packages, based on found per_config.json files"""
    persistent_root = f"{tmp_sysroot}/persistent"
    os.makedirs(persistent_root, exist_ok=True)
    return persistent_root


def artifact_output_path_impl(root_dir):
    art = f"{os.environ['TEST_UNDECLARED_OUTPUTS_DIR']}{root_dir}"
    os.makedirs(art)
    return art


@pytest.fixture(scope=get_filesystem_scope)
def tmp_sysroot(root_dir):
    return tmp_sysroot_impl(root_dir)


@pytest.fixture(scope=get_filesystem_scope)
def tmp_shm(root_dir):
    return tmp_shm_impl(root_dir)


@pytest.fixture(scope=get_filesystem_scope)
def tmp_persistent(tmp_sysroot):
    return tmp_persistent_impl(tmp_sysroot)


@pytest.fixture(scope=get_filesystem_scope)
def artifact_output_path(root_dir):
    return artifact_output_path_impl(root_dir)


def _copy_to_sandbox_sysroot(source_path, sysroot):
    sandbox_path = os.path.join(sysroot, source_path)
    os.makedirs(os.path.dirname(sandbox_path), exist_ok=True)
    shutil.copy(source_path, os.path.dirname(sandbox_path))


def _create_dir_in_sandbox_sysroot(source_path, sysroot):
    sandbox_path = os.path.join(sysroot, source_path)
    os.makedirs(os.path.dirname(sandbox_path), exist_ok=True)


def _copy_from_sandbox_sysroot(name, dst, sysroot):
    sandbox_path = os.path.join(sysroot, name)
    shutil.copy(sandbox_path, dst)


# TODO: Merge with the previous function copy_to_sandbox_sysroot?
def _copy_to_sandbox_dst_sysroot(name, dst, sysroot):
    matches = []
    for root, _, filenames in os.walk(os.getcwd()):
        for filename in sorted(fnmatch.filter(filenames, f"*{name}")):
            matches.append(os.path.join(root, filename))

    if not matches:
        raise SctfRuntimeError(
            f"No match found for requested name '{name}', make sure the file exists (see config.py - FILE_SYSTEM_PRINT for help)"
        )
    if len(matches) > 1:
        raise SctfRuntimeError(
            f"Found {len(matches)} matches for requested name '{name}': {matches}, specify a unique pattern"
        )

    shutil.copy(matches[0], os.path.join(sysroot, dst))


def _copy_tmp_filesystem(environment):
    def copy2_and_set_read(src, dst):
        """
        Function shutil.copytree uses by default shutil.copy2 as the copying function.
        The function shutil.copy2 will try to maintain permissions as-is.
        During copying the temporary file system, it turns out someipd binary copied
        into UNDECLARED_OUTPUTS is not readable after the tests, when the outputs.zip is created.
        We work around it, by adding an extra step ensuring all files are readable.
        """
        shutil.copy2(src, dst)
        os.chmod(dst, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)

    output_dir = f"{get_output_dir()}/sysroot"
    temporary_filesystem = environment.tmp_sysroot

    logger.debug(f"Copying the test temporary file system from: {temporary_filesystem} to {output_dir}")
    try:
        shutil.copytree(environment.tmp_sysroot, output_dir, copy_function=copy2_and_set_read)
    except Exception:
        pass  # Silence the error, the failures are typically temporary files
        # logger.debug(f"Could not copy all files: {ex}")


def _print_tmp_filesystem(environment):
    list_files(environment.tmp_sysroot)


@pytest.fixture
def basic_sandbox(bazel_solibs, tmp_shm, tmp_workspace, tmp_sysroot, tmp_persistent, artifact_output_path, caplog):
    """Gathers together all fixtures in one dictionary-like structure."""

    env = Bunch(
        bazel_solibs=bazel_solibs,
        tmp_shm=tmp_shm,
        tmp_workspace=str(tmp_workspace),
        tmp_sysroot=str(tmp_sysroot),
        tmp_persistent=tmp_persistent,
        artifact_output_path=artifact_output_path,
        caplog=caplog,
        create_dir_in_sandbox_dst=_create_dir_in_sandbox_sysroot,
        copy_from_sandbox=_copy_from_sandbox_sysroot,
        copy_to_sandbox=_copy_to_sandbox_sysroot,
        copy_to_sandbox_dst=_copy_to_sandbox_dst_sysroot,
        extra_mount_list=None,
    )

    env.sandbox = BwrapSandbox(env)

    yield env

    if sctf_config.FILE_SYSTEM_PRINT:
        _print_tmp_filesystem(env)

    if sctf_config.FILE_SYSTEM_COPY:
        _copy_tmp_filesystem(env)
