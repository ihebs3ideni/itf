"""The contribution registry.

Collects opaque descriptors (facts from targets) and providers (transformations).
Enforces single-source-of-truth per contract: a contract key is owned by exactly
one descriptor *or* one provider, never both and never duplicated.
"""

from __future__ import annotations

from typing import Callable, Iterable

from ctf.contracts import Provider, build_provider
from ctf.descriptor import Descriptor
from ctf.errors import DuplicateProviderError, KeyCollisionError
from ctf.target import Target


class Registry:
    """Holds descriptors and providers contributed by plugins."""

    def __init__(self) -> None:
        self._descriptors: dict[str, Descriptor] = {}
        self._providers: dict[str, Provider] = {}

    # -- descriptors -------------------------------------------------------
    def add_descriptor(self, descriptor: Descriptor) -> None:
        key = descriptor.key
        if key in self._providers:
            raise KeyCollisionError(key)
        if key in self._descriptors:
            raise DuplicateProviderError(
                key, existing=f"descriptor:{key}", new=f"descriptor:{key}"
            )
        self._descriptors[key] = descriptor

    def add_target(self, target: Target) -> None:
        for descriptor in target.descriptors():
            self.add_descriptor(descriptor)

    # -- providers ---------------------------------------------------------
    def add_provider(self, provider: Provider) -> None:
        contract = provider.provides
        if contract in self._descriptors:
            raise KeyCollisionError(contract)
        if contract in self._providers:
            raise DuplicateProviderError(
                contract, existing=self._providers[contract].name, new=provider.name
            )
        self._providers[contract] = provider

    def register(self, factory: Callable[..., object]) -> Callable[..., object]:
        """Register a ``@provides``-decorated factory. Usable as a decorator."""
        self.add_provider(build_provider(factory))
        return factory

    # -- queries -----------------------------------------------------------
    def descriptor(self, contract: str) -> Descriptor | None:
        return self._descriptors.get(contract)

    def provider(self, contract: str) -> Provider | None:
        return self._providers.get(contract)

    def has(self, contract: str) -> bool:
        return contract in self._descriptors or contract in self._providers

    def contracts(self) -> frozenset[str]:
        return frozenset(self._descriptors) | frozenset(self._providers)

    def providers(self) -> Iterable[Provider]:
        return tuple(self._providers.values())
