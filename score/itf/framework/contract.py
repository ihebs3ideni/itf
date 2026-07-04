"""Plugin contract declarations for composition validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class PluginContract:
    """Declarative contract for a plugin's capabilities and dependencies.

    Only `name`, `provides`, and `requires` matter for composition validation.
    Phases are auto-detected from implemented hook methods — no need to list them.

    Attributes:
        name: Plugin identifier used in log messages.
        provides: Capability tokens this plugin contributes (e.g. ["target"]).
        requires: Capability tokens that must exist before this plugin runs.
        description: Optional human-readable note.
    """

    name: str
    provides: list[str] = field(default_factory=list)
    requires: list[str] = field(default_factory=list)
    description: str = ""

    def __post_init__(self):
        if not self.name:
            raise ValueError("PluginContract requires a non-empty 'name'")


def plugin_contract(
    name: str,
    provides: list[str] | None = None,
    requires: list[str] | None = None,
    description: str = "",
) -> Callable[[type], type]:
    """Attach a contract to a plugin class.

    Minimal usage — just declare what you provide and what you need::

        @plugin_contract(name="my.plugin", provides=["target"])
        class MyPlugin:
            @itf_hookimpl
            def session_start_target_create(self, context):
                context.target = MyTarget()

    Phases are auto-detected from which lifecycle methods the class implements.
    You do NOT need to list them.
    """
    contract = PluginContract(
        name=name,
        provides=provides or [],
        requires=requires or [],
        description=description,
    )

    def decorator(cls: type) -> type:
        cls.__contract__ = contract
        return cls

    return decorator
