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
"""ITF core's public surface. Nothing else is exported (docs/octo-kit/11-spec-itf-engine.md §3)."""

from .engine.bringup import ExecutionError, ProbeFailed
from .engine.contexts import CollectionClosed, WrongPhase
from .engine.hooks import hookimpl
from .engine.publish import delivers, expect, provides
from .engine.scopes import InvalidScopeName
from .engine.realize import RealizationError
from .engine.registry import CrossContributorImport
from .frontends.yaml_config import load_init, load_setup, recipe_document
from .gating import requires
from .session import (
    ConfigValidationFailed,
    NotReady,
    ResolutionFailed,
    Session,
    TargetNameClash,
    compose,
    describe,
)

__all__ = [
    "hookimpl",
    "provides",
    "delivers",
    "expect",
    "requires",
    "Session",
    "describe",
    "compose",
    "CollectionClosed",
    "WrongPhase",
    "CrossContributorImport",
    "InvalidScopeName",
    "RealizationError",
    "ExecutionError",
    "ProbeFailed",
    "ResolutionFailed",
    "ConfigValidationFailed",
    "NotReady",
    "TargetNameClash",
    "load_setup",
    "load_init",
    "recipe_document",
]
