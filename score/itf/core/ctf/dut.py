"""The Device Under Test: the runtime composition result.

The DUT is not predefined. It is a *view* over the resolved dependency graph,
backed by a single session-lived :class:`~ctf.assembly.Assembly`. Resources are
resolved **lazily** on first :meth:`DUT.require` and cached for the whole run,
so a test only pays for the capabilities it uses while resolution stays
deterministic.

Multi-device support: when the root registry declares devices (via
``registry.device("name")``), each device gets its own Assembly. The DUT
provides access via ``dut["device_name"]`` which returns a DeviceProxy
backed by that device's independent assembly.

Aggregate operations (rebuild, reprovision) are exposed for mid-run recovery.
These tear down and re-realize capabilities without restarting the whole session.
"""

from __future__ import annotations

import inspect as _inspect
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator

from score.itf.core.ctf.assembly import Assembly, RunMode, analyze
from score.itf.core.ctf.errors import CapabilityDisabledError, CapabilityUnavailableError
from score.itf.core.ctf.registry import Registry
from score.itf.core.ctf.resolver import GraphResolver
from score.itf.core.ctf.target import TARGET_ANCHOR, is_anchor


class DeviceProxy:
    """Scoped view of a DUT for a specific device.

    Returned by ``dut["device_name"]``. Backed by an independent Assembly
    with its own registry, resolver, and resource cache.

    Example::

        dut["safety"].require("itf/cap/ssh")
        dut["safety"].available("itf/cap/ping")
    """

    def __init__(self, name: str, assembly: Assembly) -> None:
        self._name = name
        self._assembly = assembly
        self._disabled: set[str] = set()
        self._aliases: dict[str, str] = {}

    @property
    def device(self) -> str:
        return self._name

    def alias(self, name: str, contract: str) -> None:
        """Register a device-local alias."""
        existing = self._aliases.get(name)
        if existing is not None and existing != contract:
            raise ValueError(f"Alias '{name}' already maps to '{existing}', cannot rebind to '{contract}'")
        self._aliases[name] = contract

    def _resolve_alias(self, name_or_contract: str) -> str:
        return self._aliases.get(name_or_contract, name_or_contract)

    def require(self, contract: str) -> Any:
        """Resolve a contract within this device's assembly."""
        contract = self._resolve_alias(contract)
        if contract in self._disabled:
            raise CapabilityDisabledError(contract)
        return self._assembly.get(contract)

    def available(self, contract: str) -> bool:
        """Whether the contract fully resolves in this device's assembly."""
        contract = self._resolve_alias(contract)
        if contract in self._disabled:
            return False
        return self._assembly.available(contract)

    def __getitem__(self, name: str) -> Any:
        """Subscript access: ``dut["safety"]["ssh"]`` -- shortcut for require."""
        return self.require(name)

    def disable(self, contract: str) -> None:
        """Disable a capability in this device scope."""
        contract = self._resolve_alias(contract)
        self._disabled.add(contract)
        self._assembly.invalidate(contract)

    def enable(self, contract: str) -> None:
        """Re-enable a previously disabled capability."""
        contract = self._resolve_alias(contract)
        self._disabled.discard(contract)

    @contextmanager
    def fault(self, contract: str) -> Iterator[None]:
        """Context manager for fault injection within this device."""
        contract = self._resolve_alias(contract)
        self.disable(contract)
        try:
            yield
        finally:
            self.enable(contract)

    def invalidate(self, contract: str) -> tuple[str, ...]:
        """Invalidate a contract and its dependents in this device."""
        contract = self._resolve_alias(contract)
        return self._assembly.invalidate(contract)

    def rebuild(self, anchor: str | None = None) -> tuple[str, ...]:
        """Tear down and re-realize the device's anchor."""
        anchor = anchor or TARGET_ANCHOR
        anchor = self._resolve_alias(anchor)
        torn = self._assembly.invalidate(anchor)
        self._assembly.get(anchor)
        return torn

    def materialized(self) -> dict[str, Any]:
        """Resources instantiated so far in this device."""
        return self._assembly.materialized()

    def provides(self) -> frozenset[str]:
        """All contracts this device can resolve."""
        return self._assembly.registry.contracts()

    def inspect(self, contract: str | None = None) -> "ContractInfo | list[ContractInfo]":
        """Auto-inspect contracts in this device's assembly."""
        if contract is not None:
            contract = self._resolve_alias(contract)
            return _inspect_one(self._assembly, contract)
        return [_inspect_one(self._assembly, c) for c in sorted(self._assembly.plan.available)]

    def help(self, contract: str | None = None) -> str:
        """Human-readable help for device-scoped contracts."""
        infos = self.inspect(contract)
        if isinstance(infos, ContractInfo):
            return infos.format()
        return "\n\n".join(info.format() for info in infos)

    def __repr__(self) -> str:
        return f"DeviceProxy({self._name!r})"


class DUT:
    """A runtime composition of resolved resources.

    Provides both fine-grained contract access (require/available) and
    aggregate operations (rebuild/reprovision) for mid-run recovery.

    Supports **aliases** -- short project-level names that map to contract
    strings. Only the root-level conftest can register aliases (via the
    ``pytest_itf_aliases`` hook).

    In multi-device setups, ``dut["device"]`` returns a :class:`DeviceProxy`
    backed by that device's independent assembly.
    """

    def __init__(
        self,
        assembly: Assembly,
        device_assemblies: dict[str, Assembly] | None = None,
    ) -> None:
        self._assembly = assembly
        self._devices: dict[str, DeviceProxy] = {}
        self._disabled: set[str] = set()
        self._aliases: dict[str, str] = {}
        self._aliases_locked: bool = False

        if device_assemblies:
            for name, dev_assembly in device_assemblies.items():
                self._devices[name] = DeviceProxy(name, dev_assembly)

    # ------------------------------------------------------------------
    # Alias management
    # ------------------------------------------------------------------
    def alias(self, name: str, contract: str) -> None:
        """Register a short name that maps to a full contract string."""
        if self._aliases_locked:
            raise RuntimeError(
                f"Cannot register alias '{name}': alias table is locked. "
                "Aliases must be registered in the root conftest's "
                "pytest_itf_aliases hook, not from fixtures or sub-conftests."
            )
        existing = self._aliases.get(name)
        if existing is not None and existing != contract:
            raise ValueError(f"Alias '{name}' already maps to '{existing}', cannot rebind to '{contract}'")
        self._aliases[name] = contract

    def lock_aliases(self) -> None:
        """Lock the alias table."""
        self._aliases_locked = True

    def aliases(self) -> dict[str, str]:
        """Return a copy of the alias -> contract mapping."""
        return dict(self._aliases)

    def _resolve_alias(self, name_or_contract: str) -> str:
        return self._aliases.get(name_or_contract, name_or_contract)

    # ------------------------------------------------------------------
    # Contract access (root assembly)
    # ------------------------------------------------------------------
    def require(self, contract: str) -> Any:
        """Resolve and return a contract from the root assembly.

        Accepts both raw contract strings and registered aliases.
        """
        contract = self._resolve_alias(contract)
        if contract in self._disabled:
            raise CapabilityDisabledError(contract)
        return self._assembly.get(contract)

    def __getitem__(self, name: str) -> Any:
        """Subscript access: ``dut["shell"]`` or ``dut["device_name"]``.

        If ``name`` matches a known device, returns its DeviceProxy.
        Otherwise resolves as an alias/contract via require().
        """
        if name in self._devices:
            return self._devices[name]
        return self.require(name)

    def provides(self) -> frozenset[str]:
        """All contracts the root assembly can resolve."""
        return self._assembly.registry.contracts()

    def can_provide(self, contract: str) -> bool:
        contract = self._resolve_alias(contract)
        return self._assembly.registry.has(contract)

    def available(self, contract: str) -> bool:
        """Whether the contract fully resolves in the root assembly."""
        contract = self._resolve_alias(contract)
        if contract in self._disabled:
            return False
        return self._assembly.available(contract)

    def devices(self) -> frozenset[str]:
        """All declared device names."""
        return frozenset(self._devices)

    # ------------------------------------------------------------------
    # Capability control (root assembly)
    # ------------------------------------------------------------------
    def disable(self, contract: str) -> None:
        """Disable a capability in the root assembly."""
        contract = self._resolve_alias(contract)
        self._disabled.add(contract)
        self._assembly.invalidate(contract)

    def enable(self, contract: str) -> None:
        """Re-enable a previously disabled capability."""
        contract = self._resolve_alias(contract)
        self._disabled.discard(contract)

    @contextmanager
    def fault(self, contract: str) -> Iterator[None]:
        """Context manager for fault injection -- disable temporarily."""
        contract = self._resolve_alias(contract)
        self.disable(contract)
        try:
            yield
        finally:
            self.enable(contract)

    @property
    def disabled(self) -> frozenset[str]:
        """Currently disabled contracts in root assembly."""
        return frozenset(self._disabled)

    def materialized(self) -> dict[str, Any]:
        """Resources instantiated so far in the root assembly."""
        return self._assembly.materialized()

    # ------------------------------------------------------------------
    # Introspection / Auto-documentation
    # ------------------------------------------------------------------
    def inspect(self, contract: str | None = None) -> "ContractInfo | list[ContractInfo]":
        """Auto-inspect providers and their returned objects.

        When called with a contract, returns info for that contract.
        When called without arguments, returns info for all available contracts.
        """
        if contract is not None:
            contract = self._resolve_alias(contract)
            return _inspect_one(self._assembly, contract)
        return [_inspect_one(self._assembly, c) for c in sorted(self._assembly.plan.available)]

    def help(self, contract: str | None = None) -> str:
        """Human-readable help string for a contract or all contracts."""
        infos = self.inspect(contract)
        if isinstance(infos, ContractInfo):
            return infos.format()
        return "\n\n".join(info.format() for info in infos)

    # ------------------------------------------------------------------
    # Recovery / Aggregate operations
    # ------------------------------------------------------------------
    def invalidate(self, contract: str) -> tuple[str, ...]:
        """Invalidate a contract and its transitive dependents."""
        contract = self._resolve_alias(contract)
        return self._assembly.invalidate(contract)

    def anchors(self) -> frozenset[str]:
        """Return all anchor contracts in the root composition."""
        return frozenset(c for c in self._assembly.registry.contracts() if is_anchor(c))

    def rebuild(self, anchor: str | None = None) -> tuple[str, ...]:
        """Tear down and re-realize one or all targets from scratch."""
        if anchor is not None:
            anchor = self._resolve_alias(anchor)
            torn = self._assembly.invalidate(anchor)
            self._assembly.get(anchor)
            return torn

        all_torn: list[str] = []
        for a in sorted(self.anchors()):
            all_torn.extend(self._assembly.invalidate(a))
        for a in sorted(self.anchors()):
            self._assembly.get(a)
        return tuple(all_torn)

    def reprovision(self, anchor: str | None = None) -> None:
        """Invalidate capabilities but keep target anchor(s) alive."""
        if anchor is not None:
            anchor = self._resolve_alias(anchor)
            anchors_to_reprovision = {anchor}
        else:
            anchors_to_reprovision = self.anchors()

        for a in anchors_to_reprovision:
            dependents = self._assembly.resolver.dependents(a)
            anchor_deps = dependents - {a}
            for contract in list(anchor_deps):
                if contract in self._assembly._cache:
                    self._assembly.invalidate(contract)


# --------------------------------------------------------------------------
# Composition entry points
# --------------------------------------------------------------------------


def build_manager(registry: Registry, mode: RunMode = RunMode.LOOSE) -> Assembly:
    """Validate the graph and build the session Assembly."""
    resolver = GraphResolver(registry)
    plan = analyze(registry, resolver, mode)
    return Assembly(registry, resolver, plan)


def build_device_assemblies(registry: Registry, mode: RunMode = RunMode.LOOSE) -> dict[str, Assembly]:
    """Build an Assembly for each declared device in the registry."""
    assemblies: dict[str, Assembly] = {}
    for name in registry.device_names():
        dev_registry = registry.device_registry(name)
        if dev_registry is not None:
            assemblies[name] = build_manager(dev_registry, mode)
    return assemblies


@contextmanager
def compose(registry: Registry, mode: RunMode = RunMode.LOOSE) -> Iterator[DUT]:
    """Programmatic composition (for non-pytest use).

    Enters the session, yields a DUT, and tears everything down on exit.
    """
    assembly = build_manager(registry, mode)
    device_assemblies = build_device_assemblies(registry, mode)

    assembly.enter()
    for dev_asm in device_assemblies.values():
        dev_asm.enter()
    try:
        yield DUT(assembly, device_assemblies)
    finally:
        for dev_asm in reversed(list(device_assemblies.values())):
            dev_asm.exit()
        assembly.exit()


# --------------------------------------------------------------------------
# Introspection data structures and helpers
# --------------------------------------------------------------------------


@dataclass
class MethodInfo:
    """Describes a public method on a resolved resource."""

    name: str
    signature: str
    docstring: str | None


@dataclass
class ContractInfo:
    """Auto-generated documentation for a single contract."""

    contract: str
    kind: str  # "descriptor" | "provider" | "unknown"
    value_repr: str | None = None
    return_type: str | None = None
    docstring: str | None = None
    factory_name: str | None = None
    requires: tuple[str, ...] = ()
    public_methods: list[MethodInfo] | None = None
    public_attributes: list[str] | None = None
    is_materialized: bool = False

    def format(self) -> str:
        """Render as a human-readable help block."""
        lines: list[str] = []
        lines.append(f"{'─' * 60}")
        lines.append(f"Contract: {self.contract}")
        lines.append(f"Kind:     {self.kind}")

        if self.factory_name:
            lines.append(f"Factory:  {self.factory_name}")
        if self.return_type:
            lines.append(f"Returns:  {self.return_type}")
        if self.requires:
            lines.append(f"Requires: {', '.join(self.requires)}")
        lines.append(f"Resolved: {'yes' if self.is_materialized else 'no (lazy)'}")

        if self.docstring:
            lines.append("")
            lines.append("  " + self.docstring.replace("\n", "\n  "))

        if self.public_methods:
            lines.append("")
            lines.append("  Methods:")
            for m in self.public_methods:
                sig_line = f"    .{m.name}{m.signature}"
                lines.append(sig_line)
                if m.docstring:
                    first_line = m.docstring.split("\n")[0]
                    lines.append(f"        {first_line}")

        if self.public_attributes:
            lines.append("")
            lines.append("  Attributes:")
            for attr in self.public_attributes:
                lines.append(f"    .{attr}")

        lines.append(f"{'─' * 60}")
        return "\n".join(lines)


def _inspect_one(assembly: Assembly, contract: str) -> ContractInfo:
    """Build introspection info for a single contract."""
    registry = assembly.registry
    descriptor = registry.descriptor(contract)
    provider = registry.provider(contract)
    instance = assembly._cache.get(contract)

    if descriptor is not None:
        return ContractInfo(
            contract=contract,
            kind="descriptor",
            value_repr=repr(descriptor.value),
            return_type=type(descriptor.value).__name__ if descriptor.value is not None else None,
            docstring=None,
            factory_name=None,
            requires=(),
            public_methods=_extract_public_methods(descriptor.value) if descriptor.value is not None else [],
            public_attributes=_extract_public_attributes(descriptor.value) if descriptor.value is not None else [],
            is_materialized=True,
        )

    if provider is not None:
        factory = provider.factory
        return_type = _get_return_type(factory)
        docstring = _inspect.getdoc(factory)

        methods: list[MethodInfo] = []
        attributes: list[str] = []
        if instance is not None:
            methods = _extract_public_methods(instance)
            attributes = _extract_public_attributes(instance)
        elif return_type is not None:
            try:
                cls = _resolve_type(return_type, factory)
                if cls is not None:
                    methods = _extract_public_methods_from_class(cls)
                    attributes = _extract_public_attributes_from_class(cls)
            except Exception:
                pass

        return ContractInfo(
            contract=contract,
            kind="provider",
            value_repr=repr(instance) if instance is not None else None,
            return_type=return_type,
            docstring=docstring,
            factory_name=provider.name,
            requires=provider.requires,
            public_methods=methods,
            public_attributes=attributes,
            is_materialized=instance is not None,
        )

    return ContractInfo(contract=contract, kind="unknown")


def _get_return_type(factory: Any) -> str | None:
    try:
        hints = _inspect.get_annotations(factory, eval_str=False)
    except Exception:
        try:
            hints = getattr(factory, "__annotations__", {})
        except Exception:
            return None
    ret = hints.get("return")
    if ret is None:
        return None
    if isinstance(ret, str):
        return ret
    if isinstance(ret, type):
        return ret.__name__
    return str(ret)


def _resolve_type(type_name: str, factory: Any) -> type | None:
    module = _inspect.getmodule(factory)
    if module is not None:
        cls = getattr(module, type_name, None)
        if isinstance(cls, type):
            return cls
    return None


def _extract_public_methods(obj: Any) -> list[MethodInfo]:
    methods: list[MethodInfo] = []
    for name in sorted(dir(obj)):
        if name.startswith("_"):
            continue
        try:
            attr = getattr(type(obj), name, None) or getattr(obj, name)
        except Exception:
            continue
        if not callable(attr):
            continue
        try:
            sig = str(_inspect.signature(attr))
        except (ValueError, TypeError):
            sig = "(...)"
        doc = _inspect.getdoc(attr)
        methods.append(MethodInfo(name=name, signature=sig, docstring=doc))
    return methods


def _extract_public_methods_from_class(cls: type) -> list[MethodInfo]:
    methods: list[MethodInfo] = []
    for name in sorted(dir(cls)):
        if name.startswith("_"):
            continue
        try:
            attr = getattr(cls, name)
        except Exception:
            continue
        if not callable(attr):
            continue
        try:
            sig = str(_inspect.signature(attr))
        except (ValueError, TypeError):
            sig = "(...)"
        doc = _inspect.getdoc(attr)
        methods.append(MethodInfo(name=name, signature=sig, docstring=doc))
    return methods


def _extract_public_attributes(obj: Any) -> list[str]:
    attrs: list[str] = []
    for name in sorted(dir(obj)):
        if name.startswith("_"):
            continue
        try:
            attr = getattr(obj, name)
        except Exception:
            continue
        if callable(attr):
            continue
        attrs.append(name)
    return attrs


def _extract_public_attributes_from_class(cls: type) -> list[str]:
    attrs: list[str] = []
    for klass in cls.__mro__:
        for name in getattr(klass, "__annotations__", {}):
            if not name.startswith("_") and name not in attrs:
                attrs.append(name)
    return sorted(attrs)
