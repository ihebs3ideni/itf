"""Standalone plugin collection (no pytest session required).

To audit an ecosystem we need to know *which plugin contributed what*. CTF's
shared :class:`~ctf.registry.Registry` merges everything and would raise on the
very collisions we want to *report* -- so instead we drive each plugin's CTF
hookimpls in **isolation**, via a throwaway :mod:`pluggy` manager, and snapshot
what each one contributes. Cross-plugin analysis then happens in
:mod:`ctf_governance.catalog`.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field

import pluggy

from ctf.pytest_plugin import CtfHookSpecs
from ctf.registry import Registry
from ctf.steps import StepRegistry

#: The CTF contribution hooks, by name.
_CTF_HOOKS = frozenset({"pytest_ctf_setup", "pytest_ctf_steps"})


def _default_impl_opts() -> dict:
    """The hookimpl options pluggy assigns to a plainly-decorated function."""
    marker = pluggy.HookimplMarker("pytest")

    @marker
    def _probe() -> None: ...

    return dict(getattr(_probe, "pytest_impl"))


class _CtfPluginManager(pluggy.PluginManager):
    """A pluggy manager that also accepts *undecorated* CTF hook functions.

    Real pytest auto-detects hookimpls by their ``pytest_*`` name; the example
    plugins rely on that and omit ``@pytest.hookimpl``. Plain pluggy would skip
    them, so we mirror pytest's name-based detection for the CTF hooks.
    """

    def parse_hookimpl_opts(self, plugin: object, name: str):
        opts = super().parse_hookimpl_opts(plugin, name)
        if opts is None and name in _CTF_HOOKS:
            method = getattr(plugin, name)
            if inspect.isroutine(method):
                opts = _default_impl_opts()
        return opts



@dataclass(frozen=True)
class ProviderInfo:
    contract: str
    name: str
    phase: str
    requires: tuple[str, ...]
    is_generator: bool


@dataclass
class Contribution:
    """What a single plugin contributes to the ecosystem."""

    plugin: str
    descriptors: set[str] = field(default_factory=set)
    providers: dict[str, ProviderInfo] = field(default_factory=dict)
    #: extension point -> contributed step names.
    steps: dict[str, list[str]] = field(default_factory=dict)
    #: extension point -> policy name (as seen by this plugin).
    policies: dict[str, str] = field(default_factory=dict)

    def provided_contracts(self) -> set[str]:
        return set(self.descriptors) | set(self.providers)


def _plugin_name(plugin: object) -> str:
    return getattr(plugin, "__name__", None) or type(plugin).__name__


def inspect_plugin(plugin: object, name: str | None = None) -> Contribution:
    """Run ``plugin``'s CTF hookimpls alone and snapshot its contributions."""
    pm = _CtfPluginManager("pytest")
    pm.add_hookspecs(CtfHookSpecs)
    pm.register(plugin)

    registry = Registry()
    steps = StepRegistry()
    pm.hook.pytest_ctf_setup(registry=registry, config=None)
    pm.hook.pytest_ctf_steps(steps=steps, config=None)

    contribution = Contribution(plugin=name or _plugin_name(plugin))
    for contract in registry.contracts():
        provider = registry.provider(contract)
        if provider is not None:
            contribution.providers[contract] = ProviderInfo(
                contract=contract,
                name=provider.name,
                phase=provider.phase,
                requires=tuple(provider.requires),
                is_generator=provider.is_generator,
            )
        else:
            contribution.descriptors.add(contract)

    for point in steps.points():
        names = [s.name for s in steps.steps_for(point)]
        if names:
            contribution.steps[point] = names
            contribution.policies[point] = steps.policy(point).name
    return contribution


def collect(*plugins: object) -> list[Contribution]:
    """Inspect several plugins, each in isolation."""
    return [inspect_plugin(p) for p in plugins]


__all__ = ["ProviderInfo", "Contribution", "inspect_plugin", "collect"]
