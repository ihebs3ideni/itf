"""Resource lifecycle management.

A :class:`LifecycleScope` instantiates provider factories and records teardown
callables. Providers may be plain functions (value only) or **generator
functions** that ``yield`` the resource; code after the ``yield`` runs at
teardown. Teardown executes in **reverse instantiation order**, mirroring
pytest's yield-fixture semantics.
"""

from __future__ import annotations

from types import GeneratorType
from typing import Any, Callable, Sequence

from score.itf.core.ctf.contracts import Provider
from score.itf.core.ctf.errors import CompositionError


class LifecycleScope:
    """Instantiates resources and tears them down deterministically."""

    def __init__(self) -> None:
        self._teardowns: list[tuple[str, Callable[[], None]]] = []
        self._closed = False

    def instantiate(self, provider: Provider, args: Sequence[Any]) -> Any:
        """Build the resource for ``provider`` using resolved ``args``."""
        if self._closed:
            raise CompositionError("cannot instantiate in a closed LifecycleScope")

        value, finalizer = instantiate_provider(provider, args)
        if finalizer is not None:
            self._teardowns.append((provider.name, finalizer))
        return value

    def close(self) -> None:
        """Run all teardowns in reverse order, aggregating failures."""
        if self._closed:
            return
        self._closed = True
        errors: list[BaseException] = []
        while self._teardowns:
            _name, finalize = self._teardowns.pop()
            try:
                finalize()
            except BaseException as exc:  # noqa: BLE001 - collect and re-raise
                errors.append(exc)
        if errors:
            raise CompositionError(f"{len(errors)} teardown(s) failed: " + "; ".join(repr(e) for e in errors))

    def __enter__(self) -> "LifecycleScope":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


def _make_finalizer(name: str, generator: GeneratorType) -> Callable[[], None]:
    def finalize() -> None:
        try:
            next(generator)
        except StopIteration:
            return
        raise CompositionError(f"generator provider {name!r} yielded more than once")

    return finalize


def instantiate_provider(provider: Provider, args: Sequence[Any]) -> tuple[Any, Callable[[], None] | None]:
    """Build a resource, returning ``(value, finalizer_or_None)``.

    Shared by :class:`LifecycleScope` (single teardown stack) and
    :class:`~ctf.assembly.Assembly` (per-contract teardown for phase re-entry),
    so generator handling lives in exactly one place.
    """
    if not provider.is_generator:
        return provider.factory(*args), None

    generator = provider.factory(*args)
    if not isinstance(generator, GeneratorType):  # pragma: no cover - defensive
        raise CompositionError(f"provider {provider.name!r} was detected as a generator but did not return a generator")
    try:
        value = next(generator)
    except StopIteration as exc:  # pragma: no cover - misuse
        raise CompositionError(f"generator provider {provider.name!r} did not yield a resource") from exc
    return value, _make_finalizer(provider.name, generator)
