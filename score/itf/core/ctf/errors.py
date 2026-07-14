"""Exception hierarchy for the composition engine.

All engine failures derive from :class:`CompositionError` so callers can catch
composition problems distinctly from arbitrary runtime errors raised inside
provider factories.
"""

from __future__ import annotations


class CompositionError(Exception):
    """Base class for all composition-engine failures."""


class UnresolvedContractError(CompositionError):
    """A required contract has no descriptor and no provider."""

    def __init__(self, contract: str, required_by: str | None = None) -> None:
        self.contract = contract
        self.required_by = required_by
        if required_by is None:
            message = f"no descriptor or provider satisfies contract {contract!r}"
        else:
            message = f"contract {contract!r} required by {required_by!r} is not provided by any descriptor or provider"
        super().__init__(message)


class CapabilityUnavailableError(Exception):
    """An additive capability could not be resolved in LOOSE mode.

    This is deliberately *not* a :class:`CompositionError`: the target spine is
    intact, so the run is valid. It signals that a specific test-facing
    capability is missing its dependencies, which the pytest adapter turns into
    a *skip* for tests that require it -- rather than aborting the session.
    """

    def __init__(self, contract: str, reason: str) -> None:
        self.contract = contract
        self.reason = reason
        super().__init__(f"capability {contract!r} is unavailable: {reason}")


class CapabilityDisabledError(Exception):
    """A capability was explicitly disabled via DUT.disable().

    Like CapabilityUnavailableError, this is not a CompositionError: the graph
    is valid but the user explicitly turned off this contract at runtime.
    """

    def __init__(self, contract: str) -> None:
        self.contract = contract
        super().__init__(f"capability {contract!r} is disabled")


class DuplicateProviderError(CompositionError):
    """Two providers claim the same contract, or a provider redefines a key."""

    def __init__(self, contract: str, existing: str, new: str) -> None:
        self.contract = contract
        super().__init__(f"contract {contract!r} is already provided by {existing!r}; cannot register {new!r}")


class KeyCollisionError(CompositionError):
    """A contract is claimed by both a descriptor and a provider."""

    def __init__(self, contract: str) -> None:
        self.contract = contract
        super().__init__(
            f"contract {contract!r} is published as a descriptor and also "
            "provided by a provider; a contract must have a single source"
        )


class CyclicDependencyError(CompositionError):
    """The dependency graph contains a cycle."""

    def __init__(self, cycle: list[str]) -> None:
        self.cycle = cycle
        super().__init__("dependency cycle detected: " + " -> ".join(cycle))
