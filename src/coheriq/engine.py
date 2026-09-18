# This code is a Qiskit project.
#
# (C) Copyright IBM 2026.
#
# This code is licensed under the Apache License, Version 2.0. You may
# obtain a copy of this license in the LICENSE.txt file in the root directory
# of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
#
# Any modifications or derivative works of this code must retain this
# copyright notice, and modified files need to carry a notice indicating
# that they have been altered from the originals.

"""Contains the AccelerationEngine class and supporting code."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from enum import Enum
from threading import Lock
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing_extensions import Self

from .domain import _DomainState, _get_domain_by_name
from .exceptions import (
    CoheriqEngineError,
    CoheriqEngineInheritanceError,
)


class _EngineState(Enum):
    # State chart:
    #
    # 1 --> 2 --> 3
    CONSTRUCTING = 1
    MATERIALIZED = 2
    ENABLED = 3


class AccelerationEngine:
    """An accelerated re-implementation of (a subset of) the functionality in a domain."""

    def __init__(self, domain_name: str, engine_name: str, bases: Sequence[Self | str] = (), /):
        """Create an engine named ``engine_name`` for the existing domain ``domain_name``."""
        try:
            domain = _get_domain_by_name(domain_name)
        except KeyError:
            raise CoheriqEngineError(
                f"No domain named '{domain_name}' has been registered"
            ) from None
        if not isinstance(engine_name, str):
            raise CoheriqEngineError("engine name must be a string")
        if not engine_name:
            raise CoheriqEngineError("engine name cannot be empty")
        self._state = _EngineState.CONSTRUCTING
        self._domain_name = domain_name
        self._domain = domain
        self._engine_name = engine_name
        self._dict: dict[str, Callable] = {}
        self._lock = Lock()
        self._impl: type
        with domain._lock:
            # An engine inherits from its domain's class and validates its
            # overrides against the domain's candidate set, so the domain must
            # have closed that set before an engine can be built against it.
            if domain._state == _DomainState.CONSTRUCTING:
                raise CoheriqEngineError(
                    f"Domain '{domain._name}' must be materialized before an engine "
                    f"can be created for it"
                )
            # Resolve bases
            resolved: list[AccelerationEngine] = []
            for base in bases:
                if isinstance(base, str):
                    try:
                        base_engine = domain._engine_registry[base]
                    except KeyError:
                        raise CoheriqEngineInheritanceError(f"Base not found: {base}") from None
                else:
                    base_engine = base
                if not isinstance(base_engine, AccelerationEngine):
                    raise CoheriqEngineError(
                        f"Base must be an AccelerationEngine or engine name, "
                        f"got {type(base_engine).__name__} instead"
                    )
                if base_engine._domain is not domain:
                    raise CoheriqEngineError(
                        f"Base engine '{base_engine._engine_name}' belongs to domain "
                        f"'{base_engine._domain_name}', not '{domain_name}'"
                    )
                resolved.append(base_engine)
            self._bases = tuple(resolved)
            # Add to registry
            if engine_name in domain._engine_registry:
                raise CoheriqEngineError("engine name has already been used")
            domain._engine_registry[engine_name] = self

    def override(
        self, func: Callable | str | None = None, /, *, name: str | None = None
    ) -> Callable:
        """Register ``func`` as this engine's override for a domain candidate."""
        # Do the right thing in the case where somebody passed the `name` in
        # place of `func`.
        if isinstance(func, str):
            if name is None:
                name = func
                func = None
            else:
                raise TypeError("Expecting a callable, got a string instead")

        def decorator(f: Callable) -> Callable:
            nonlocal name
            if name is None:
                name = f.__name__
            if not isinstance(name, str):
                raise CoheriqEngineError(
                    f"name must be None or a string, got {type(f).__name__} instead"
                )

            if name not in self._domain._dict:
                raise CoheriqEngineError(
                    f"Name '{name}' is not defined in domain '{self._domain._name}'"
                )

            with self._lock:
                if self._state != _EngineState.CONSTRUCTING:
                    raise CoheriqEngineError(
                        "Cannot mark a function after the domain is materialized"
                    )
                self._dict[name] = f

            return f

        if func is None:
            return decorator
        return decorator(func)

    def materialize(self) -> None:
        """Declare that this engine has completely specified its overrides.

        This will lock in this engine's overrides, composing them with its bases and the domain.
        """
        # These reads are intentionally unlocked.  self._bases is assigned once,
        # in __init__, and never mutated; each base's _state and _impl are
        # likewise set once by its own materialize() and never change
        # afterwards.  So there is no mutation here to synchronize against.
        for base in self._bases:
            if base._state != _EngineState.MATERIALIZED:
                raise CoheriqEngineError(
                    f"Base engine '{base._engine_name}' must be materialized before "
                    f"engine '{self._engine_name}' can be materialized, but its state "
                    f"is {base._state}"
                )
        bases = tuple(base._impl for base in self._bases)

        # Reading ``self._domain._base`` needs no domain lock: it is assigned
        # exactly once, when the domain materializes, and never reassigned.
        # __init__ guarantees the domain was already materialized before this
        # engine existed, so that write happens-before any read here.
        with self._lock:
            if self._state != _EngineState.CONSTRUCTING:
                raise CoheriqEngineError(
                    "Cannot materialize a domain that has already been materialized"
                )
            self._impl = type(self._engine_name, (*bases, self._domain._base), self._dict)
            del self._dict
            self._state = _EngineState.MATERIALIZED
