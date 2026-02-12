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
import os
import shutil
import logging
from score.sctf.exception import SctfRuntimeError


logger = logging.getLogger(__name__)


def is_file_executable(path):
    """
    Checks whether path points to a valid executable.
    :param path: target path to be checked
    :return: boolean value True, if the path is a valid executable, False otherwise
    """
    return shutil.which(path) is not None


def find_binary(filename):
    """
    Recursively search for given filename starting from the current working directory.
    This is a convenience function to allow for shorter filenames used in the test, without full path qualification.
    :param filename: name of the binary to be found
    :return: full path of the found binary or the filename itself if it is not a file basename
    :raise: SctfRuntimeError if no binary or multiple matching binaries were found
    """
    if "/" not in filename:
        found_paths = []
        for dirpath, _, filenames in os.walk("."):
            if filename in filenames:
                found_paths.append(os.path.join(dirpath, filename))

        if not found_paths:
            raise SctfRuntimeError("No path found.")
        if len(found_paths) > 1:
            raise SctfRuntimeError("Filename is not unique.")

        return found_paths[0]

    return filename


def list_files(startpath):
    """
    Recursively prints the contents of the file system starting at given location
    Original solution to this
    :param startpath: absolute or relative path to starting printing from
    """
    if not os.path.exists(startpath):
        logger.error(f"Requested start directory does not exist or is inaccessible: {startpath}")
        return

    indent_size = 2
    log_lines = []
    for root, _, files in os.walk(startpath):
        level = root.replace(startpath, "").count(os.sep)
        log_lines.append(f"{' ' * indent_size * level}{os.path.basename(root)}/")
        for f in files:
            log_lines.append(f"{' ' * indent_size * (level + 1)}{f}")

    logger.debug("Printing file tree starting at position %s:\n%s", startpath, "\n".join(log_lines))
