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
"""Which composition a run uses, said once in the project's own configuration.

`resolve` finds the composition (a file, or inline YAML/JSON text) from, in order:

1. the explicit value a runner hands in (`--itf-target`, the `itf_target` ini option, `Session(target=...)`),
2. the environment variable `ITF_TARGET`,
3. `[tool.itf] target` in `pyproject.toml` at the project root,
4. `ITF_TARGET_DOCUMENT`, the document a build system generated for the run.

`resolve_overrides` does the same for override files (`--itf-override`, `ITF_OVERRIDE`, `[tool.itf] override`):
each is a composition holding only what changes, merged by role over the target. The module is
runner-neutral: a test runner, the command line and a plain script all go through it.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml


logger = logging.getLogger(__name__)

ENV_TARGET = "ITF_TARGET"
ENV_OVERRIDE = "ITF_OVERRIDE"
ENV_DOCUMENT = "ITF_TARGET_DOCUMENT"


class TargetSourceError(ValueError):
    """A configured composition cannot be used: it names no file and is not YAML/JSON text."""


@dataclass(frozen=True)
class TargetSource:
    """`value` is an absolute path, or inline YAML/JSON text; `origin` says where it was configured."""

    value: str
    origin: str

    @property
    def is_inline(self) -> bool:
        return not _is_file(self.value)

    def describe(self) -> str:
        value = "<inline>" if self.is_inline else self.value
        return f"{value} (from {self.origin})"


def _is_file(value: str) -> bool:
    try:
        return Path(value).is_file()
    except (OSError, ValueError):  # multiline text is not a file name
        return False


def _inline_document(value: str) -> bool:
    try:
        return isinstance(yaml.safe_load(value), Mapping)
    except yaml.YAMLError:
        return False


def _directories(root, search: Iterable) -> list[Path]:
    found = [Path.cwd()]
    for directory in (root, *search):
        if directory is not None and Path(directory) not in found:
            found.append(Path(directory))
    return found


def _locate(value: str, origin: str, directories: list[Path]) -> TargetSource:
    text = value.strip()
    path = Path(text)
    if "\n" not in text:
        candidates = [path] if path.is_absolute() else [d / path for d in directories]
        for candidate in candidates:
            if candidate.is_file():
                return TargetSource(str(candidate.resolve()), origin)
    if _inline_document(text):
        return TargetSource(value, origin)
    tried = ", ".join(str(d) for d in directories) if not path.is_absolute() else str(path.parent)
    raise TargetSourceError(
        f"composition {text[:80]!r} (from {origin}) is not an existing file and not inline YAML/JSON text; "
        f"looked in: {tried}"
    )


def pyproject_value(root, key: str) -> str | None:
    """`[tool.itf] <key>` in `pyproject.toml` at `root`, or None."""
    if root is None:
        return None
    pyproject = Path(root) / "pyproject.toml"
    if not pyproject.is_file():
        return None
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib
        except ImportError:
            if "[tool.itf]" in pyproject.read_text(encoding="utf-8"):
                raise TargetSourceError(f"{pyproject} has [tool.itf], and no TOML reader is installed (tomli)")
            return None
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise TargetSourceError(f"{pyproject} is not valid TOML: {exc}") from exc
    value = (data.get("tool", {}).get("itf", {}) or {}).get(key)
    if value is not None and not isinstance(value, str):
        raise TargetSourceError(f"{pyproject}: [tool.itf] {key} must be a string, not {type(value).__name__}")
    return value or None


def resolve(
    explicit: str | None = None,
    *,
    environ: Mapping[str, str] = os.environ,
    root=None,
    search: Iterable = (),
    explicit_origin: str = "explicit",
) -> TargetSource | None:
    """The composition this run uses, or None when none is configured. Raises `TargetSourceError` for a
    configured value that is neither an existing file nor inline text.

    A relative path is tried against the current directory, then `root`, then each directory in
    `search`; a path from `pyproject.toml` is tried against `root` first. `explicit_origin` names
    the runner's own setting in messages (for example "--itf-target")."""
    directories = _directories(root, tuple(search))
    for value, origin in ((explicit, explicit_origin), (environ.get(ENV_TARGET), ENV_TARGET)):
        if value and value.strip():
            return _locate(value, origin, directories)
    configured = pyproject_value(root, "target")
    if configured:
        first = [Path(root), *(d for d in directories if d != Path(root))]
        return _locate(configured, "pyproject.toml [tool.itf] target", first)
    document = environ.get(ENV_DOCUMENT)
    if document and document.strip():
        return _locate(document, ENV_DOCUMENT, directories)
    return None


def resolve_overrides(
    explicit: Iterable[str] = (),
    *,
    environ: Mapping[str, str] = os.environ,
    root=None,
    search: Iterable = (),
    explicit_origin: str = "explicit",
) -> tuple[TargetSource, ...]:
    """The override files this run uses, in merge order: the runner's own values, else `ITF_OVERRIDE`
    (paths separated by the OS path separator), else `[tool.itf] override`."""
    directories = _directories(root, tuple(search))
    values = [(v, explicit_origin) for v in explicit if v and v.strip()]
    if not values and environ.get(ENV_OVERRIDE):
        values = [(v, ENV_OVERRIDE) for v in environ[ENV_OVERRIDE].split(os.pathsep) if v.strip()]
    if not values:
        configured = pyproject_value(root, "override")
        values = [(configured, "pyproject.toml [tool.itf] override")] if configured else []
    return tuple(_locate(v, origin, directories) for v, origin in values)


def as_source(composition: Any, *, root=None, search: Iterable = (), origin: str = "target=") -> TargetSource:
    """`composition` as a `TargetSource`: one is returned as is; a path or text is located and checked."""
    if isinstance(composition, TargetSource):
        return composition
    return _locate(str(composition), origin, _directories(root, tuple(search)))
