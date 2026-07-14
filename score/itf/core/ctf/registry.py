"""The contribution registry.

Collects opaque descriptors (facts from targets) and providers (transformations).
Enforces single-source-of-truth per contract: a contract key is owned by exactly
one descriptor *or* one provider, never both and never duplicated.

Registries form a parent-child hierarchy for multi-device setups. Each device
gets its own child registry. Descriptor lookups cascade to the parent (shared
facts are visible to all devices); provider lookups are local-only (each device
must explicitly register its own providers).
"""

from __future__ import annotations

from typing import Callable, Iterable

from score.itf.core.ctf.contracts import Provider, build_provider
from score.itf.core.ctf.descriptor import Descriptor
from score.itf.core.ctf.errors import DuplicateProviderError, KeyCollisionError
from score.itf.core.ctf.target import Target


class Registry:
    """Holds descriptors and providers contributed by plugins.

    Args:
        parent: Optional parent registry. Descriptor lookups that miss locally
            cascade to the parent (enabling shared facts across devices).
    """

    def __init__(self, parent: "Registry | None" = None) -> None:
        self._parent = parent
        self._descriptors: dict[str, Descriptor] = {}
        self._providers: dict[str, Provider] = {}
        self._devices: dict[str, "Registry"] = {}
        self._bindings: dict[str, dict[str, str]] = {}
        self._bindings_locked: bool = False

    @property
    def parent(self) -> "Registry | None":
        return self._parent

    # -- descriptors -------------------------------------------------------
    def add_descriptor(self, descriptor: Descriptor) -> None:
        key = descriptor.key
        if key in self._providers:
            raise KeyCollisionError(key)
        if key in self._descriptors:
            raise DuplicateProviderError(key, existing=f"descriptor:{key}", new=f"descriptor:{key}")
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
            raise DuplicateProviderError(contract, existing=self._providers[contract].name, new=provider.name)
        self._providers[contract] = provider

    def register(self, factory: Callable[..., object]) -> Callable[..., object]:
        """Register a @provides-decorated factory. Usable as a decorator."""
        self.add_provider(build_provider(factory))
        return factory

    # -- bindings (requirement redirects) ----------------------------------
    def bind(self, provider_contract: str, old_requirement: str, new_requirement: str) -> None:
        """Redirect a provider's dependency to a different contract.

        After bind("itf/cap/udp", "itf/net/ip_address", "itf/net/heartbeat_ip"),
        the provider for itf/cap/udp will receive the resource from
        itf/net/heartbeat_ip where it originally asked for itf/net/ip_address.
        """
        if self._bindings_locked:
            raise RuntimeError(
                f"Cannot bind '{provider_contract}': bindings are locked. "
                "Bindings must be registered in the root conftest's "
                "pytest_itf_bindings hook."
            )
        if provider_contract not in self._providers:
            raise ValueError(f"Cannot bind: no provider registered for '{provider_contract}'")
        provider = self._providers[provider_contract]
        if old_requirement not in provider.requires:
            raise ValueError(
                f"Provider '{provider_contract}' does not require '{old_requirement}' (has: {provider.requires})"
            )
        self._bindings.setdefault(provider_contract, {})[old_requirement] = new_requirement

    def apply_bindings(self) -> None:
        """Rewrite provider requires tuples according to registered bindings."""
        for contract, redirects in self._bindings.items():
            provider = self._providers[contract]
            new_requires = tuple(redirects.get(r, r) for r in provider.requires)
            self._providers[contract] = Provider(
                provides=provider.provides,
                factory=provider.factory,
                requires=new_requires,
                name=provider.name,
            )
        self._bindings_locked = True

    def lock_bindings(self) -> None:
        """Lock bindings without applying (used when no bindings registered)."""
        self._bindings_locked = True

    def bindings(self) -> dict[str, dict[str, str]]:
        """Return a copy of the binding table for diagnostics."""
        return {k: dict(v) for k, v in self._bindings.items()}

    # -- device scoping ----------------------------------------------------
    def device(self, name: str) -> "DeviceRegistryContext":
        """Return a scoped context for registering into a device-local registry.

        Each device gets its own Registry (child of this one). Descriptors in
        the parent are visible to the child via fallback resolution -- shared
        facts don't need to be repeated per device.

        Providers are local: the same generic plugin factory can be registered
        into multiple device scopes and each resolves independently::

            with registry.device("safety") as dev:
                dev.add_descriptor(Descriptor("itf/net/ssh_endpoint", {...}))
                dev.register(ssh_capability)

            with registry.device("integ") as dev:
                dev.add_descriptor(Descriptor("itf/net/ssh_endpoint", {...}))
                dev.register(ssh_capability)
        """
        if name not in self._devices:
            self._devices[name] = Registry(parent=self)
        return DeviceRegistryContext(self._devices[name])

    def device_registry(self, name: str) -> "Registry | None":
        """Return the child registry for a device, or None."""
        return self._devices.get(name)

    def device_names(self) -> frozenset[str]:
        """Names of all declared devices."""
        return frozenset(self._devices)

    # -- queries -----------------------------------------------------------
    def descriptor(self, contract: str) -> Descriptor | None:
        """Look up a descriptor locally, then cascade to parent."""
        local = self._descriptors.get(contract)
        if local is not None:
            return local
        if self._parent is not None:
            return self._parent.descriptor(contract)
        return None

    def provider(self, contract: str) -> Provider | None:
        """Look up a provider (local only -- no parent fallback)."""
        return self._providers.get(contract)

    def has(self, contract: str) -> bool:
        """Whether this registry can satisfy the contract.

        Checks local descriptors/providers, then parent descriptors only
        (parent providers don't cascade).
        """
        if contract in self._descriptors or contract in self._providers:
            return True
        if self._parent is not None:
            return self._parent.descriptor(contract) is not None
        return False

    def contracts(self) -> frozenset[str]:
        """All contracts resolvable from this scope.

        Includes local providers + local descriptors + inherited descriptors
        from parent. Parent *providers* are NOT included (they don't cascade).
        """
        local = frozenset(self._descriptors) | frozenset(self._providers)
        if self._parent is not None:
            # Only inherit descriptors from parent chain
            return local | self._parent._all_descriptors()
        return local

    def _all_descriptors(self) -> frozenset[str]:
        """All descriptor keys in this registry and its parent chain."""
        local = frozenset(self._descriptors)
        if self._parent is not None:
            return local | self._parent._all_descriptors()
        return local

    def local_contracts(self) -> frozenset[str]:
        """Only contracts registered directly in this registry."""
        return frozenset(self._descriptors) | frozenset(self._providers)

    def providers(self) -> Iterable[Provider]:
        """All providers registered in this scope (local only)."""
        return tuple(self._providers.values())


class DeviceRegistryContext:
    """Scoped context for registering into a device-local Registry.

    Contracts are plain strings -- no tagging, no mangling. The same generic
    @provides("itf/cap/ssh") factory can be registered into multiple device
    scopes independently.
    """

    def __init__(self, registry: Registry) -> None:
        self._registry = registry

    @property
    def registry(self) -> Registry:
        """The underlying device registry."""
        return self._registry

    def __enter__(self) -> "DeviceRegistryContext":
        return self

    def __exit__(self, *args: object) -> None:
        pass

    def register(self, factory: Callable[..., object]) -> Callable[..., object]:
        """Register a @provides-decorated factory into the device registry."""
        self._registry.register(factory)
        return factory

    def add_provider(self, provider: Provider) -> None:
        """Register a Provider into the device registry."""
        self._registry.add_provider(provider)

    def add_descriptor(self, descriptor: Descriptor) -> None:
        """Register a Descriptor into the device registry."""
        self._registry.add_descriptor(descriptor)
