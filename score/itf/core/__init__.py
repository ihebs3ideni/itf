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
"""ITF core's public surface. Nothing else is exported."""

from .engine.bringup import ExecutionError, ProbeFailed
from .engine.hooks import hookimpl
from .engine.packs import PackNotFound
from .engine.publish import DuplicateLabel, capability, state
from .engine.scopes import InvalidScopeName
from .engine.realize import RealizationError
from .engine.registry import CrossContributorImport
from .frontends.composition import CompositionError
from .frontends.target_source import TargetSource, TargetSourceError
from .frontends.target_source import resolve as resolve_target
from .frontends.target_source import resolve_overrides
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
    "capability",
    "state",
    "requires",
    "Session",
    "describe",
    "compose",
    "CrossContributorImport",
    "CompositionError",
    "DuplicateLabel",
    "InvalidScopeName",
    "PackNotFound",
    "RealizationError",
    "ExecutionError",
    "ProbeFailed",
    "ResolutionFailed",
    "ConfigValidationFailed",
    "NotReady",
    "TargetNameClash",
    "TargetSource",
    "TargetSourceError",
    "resolve_target",
    "resolve_overrides",
]
