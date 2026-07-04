"""Context hub for plugin coordination via typed state channels."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar, Optional, Callable

T = TypeVar("T")


class ContextState(Generic[T]):
    """Typed state container owned by a specific plugin.

    Prevents string-key collisions and enables IDE completion.
    """

    def __init__(self, state_type: type[T], owner: str, factory: Callable[[], T] | None = None):
        self.state_type = state_type
        self.owner = owner
        self.factory = factory
        self._value: T | None = None
        self._initialized = False

    def get_or_init(self) -> T:
        """Get value, initializing if needed."""
        if not self._initialized and self.factory:
            self._value = self.factory()
            self._initialized = True
        return self._value

    def set(self, value: T) -> None:
        """Set value."""
        self._value = value
        self._initialized = True

    def get(self) -> T | None:
        """Get value, or None if not initialized."""
        return self._value if self._initialized else None


@dataclass
class ItfContext:
    """Central context hub for plugin coordination.

    Channels:
    - target: The target under test (mocked or real)
    - target_capability_specs: Capabilities declared by target
    - capabilities: Union of all available capabilities
    - shared_resources: Shared non-test-specific resources (config, services)
    - extension_state: Typed state owned by plugins (type -> value)
    - metadata: Untyped key-value metadata
    - pytest_config: pytest Config object for option access
    - startup_checks: List of OracleResult from readiness checks
    """

    target: Any = None
    target_capability_specs: dict[str, Any] = field(default_factory=dict)
    capabilities: set[str] = field(default_factory=set)
    shared_resources: dict[str, Any] = field(default_factory=dict)
    extension_state: dict[type, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    pytest_config: Any = None
    startup_checks: list[Any] = field(default_factory=list)
    test_oracle_checks: dict[str, list[Any]] = field(default_factory=dict)
    test_raw_outcomes: dict[str, str] = field(default_factory=dict)
    test_final_outcomes: dict[str, str] = field(default_factory=dict)
    run_oracle_checks: list[Any] = field(default_factory=list)
    run_final_outcome: str | None = None

    # Internal
    _cleanup_callbacks: list[Callable[[], None]] = field(default_factory=list)
    _state_containers: dict[type, ContextState] = field(default_factory=dict)

    def use_state(
        self,
        state_type: type[T],
        owner: str = "unknown",
        factory: Callable[[], T] | None = None,
    ) -> T:
        """Get or initialize typed state.

        Args:
            state_type: The type of state to manage
            owner: Plugin name owning this state
            factory: Callable to initialize state if missing

        Returns:
            The state value, initializing if needed

        Example:
            @dataclass
            class MyPluginState:
                config: dict

            state = context.use_state(MyPluginState, owner="my_plugin",
                                     factory=lambda: MyPluginState(config={}))
            state.config["key"] = "value"
        """
        if state_type not in self._state_containers:
            self._state_containers[state_type] = ContextState(
                state_type=state_type,
                owner=owner,
                factory=factory,
            )

        container = self._state_containers[state_type]
        value = container.get_or_init()

        if state_type not in self.extension_state:
            self.extension_state[state_type] = value

        return value

    def get_state(self, state_type: type[T]) -> T | None:
        """Get typed state without initialization.

        Args:
            state_type: The type of state to retrieve

        Returns:
            The state value, or None if not initialized
        """
        return self.extension_state.get(state_type)

    def set_state(self, state_type: type[T], value: T) -> None:
        """Set typed state explicitly.

        Args:
            state_type: The type of state
            value: The value to set
        """
        self.extension_state[state_type] = value
        if state_type in self._state_containers:
            self._state_containers[state_type].set(value)

    def add_cleanup_callback(self, callback: Callable[[], None]) -> None:
        """Register a cleanup callback (called in reverse order at teardown).

        Args:
            callback: Function to call during cleanup
        """
        self._cleanup_callbacks.append(callback)

    def run_cleanup(self) -> None:
        """Execute cleanup callbacks in reverse order."""
        for callback in reversed(self._cleanup_callbacks):
            try:
                callback()
            except Exception as exc:
                # Log but continue with other cleanups
                print(f"[ERROR] Cleanup callback failed: {exc}")

    def stash_set(self, namespace: str, key: str, value: Any) -> None:
        """Set a namespaced value (legacy; prefer use_state).

        Args:
            namespace: Namespace prefix
            key: Key within namespace
            value: Value to store
        """
        stash_key = f"{namespace}:{key}"
        self.metadata[stash_key] = value

    def stash_get(self, namespace: str, key: str, default: Any = None) -> Any:
        """Get a namespaced value (legacy; prefer get_state).

        Args:
            namespace: Namespace prefix
            key: Key within namespace
            default: Default value if not found

        Returns:
            Stored value or default
        """
        stash_key = f"{namespace}:{key}"
        return self.metadata.get(stash_key, default)
