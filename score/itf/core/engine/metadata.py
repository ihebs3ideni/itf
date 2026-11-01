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
"""Contributor metadata: the `pack.yaml` that sits next to a contributor's package.

Core reads one thing from it: the pack's `name`. Everything else in the file belongs to the tools that read
it. Code with no `pack.yaml` above it is not a pack: it is the project's own, and its pack is `project`. Which
contracts a pack fulfils, and at which major, is not here: the `@capability`/`@state` decorators say it.
"""

from __future__ import annotations

import functools
import logging
import sys
from pathlib import Path

import yaml

METADATA_FILE = "pack.yaml"
logger = logging.getLogger("score.itf.core")


@functools.cache
def _read(directory: Path) -> dict | None:
    """The metadata found at `directory` or in its nearest parent holding the file, else None."""
    for candidate in (directory, *directory.parents):
        file = candidate / METADATA_FILE
        if file.is_file():
            try:
                data = yaml.safe_load(file.read_text(encoding="utf-8"))
            except (OSError, yaml.YAMLError) as exc:
                logger.warning("contributor metadata %s is unreadable: %s", file, exc)
                return None
            return data if isinstance(data, dict) else None
    return None


def contributor_metadata(module) -> dict | None:
    """The metadata of the contributor `module` (a module or its name) belongs to, or None."""
    if isinstance(module, str):
        module = sys.modules.get(module)
    file = getattr(module, "__file__", None)
    if not file:
        return None
    return _read(Path(file).resolve().parent)


PROJECT_PACK = "project"


def pack_name(metadata: dict | None) -> str:
    """The pack's name: `name` in its `pack.yaml`; code outside any pack belongs to the pack `project`."""
    name = (metadata or {}).get("name")
    return name if isinstance(name, str) and name else PROJECT_PACK
