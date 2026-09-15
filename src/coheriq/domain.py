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

"""Contains the AccelerationDomain class and supporting code."""

from __future__ import annotations

import functools
import os
from collections.abc import Callable
from enum import Enum
from inspect import isclass
from threading import Lock
from typing import TYPE_CHECKING

from .exceptions import (
    CoheriqDomainError,
)

if TYPE_CHECKING:
    from .engine import AccelerationEngine

_domain_registry_lock = Lock()
_domain_registry: dict[str, AccelerationDomain] = {}


def _get_domain_by_name(name: str) -> AccelerationDomain:
    """Return the domain with the given name; raises KeyError if not found."""
    with _domain_registry_lock:
        return _domain_registry[name]


class _DomainState(Enum):
    # State chart:
    #
    # 1 --> 2 --> 3
    #        \
    #         --> 4
    CONSTRUCTING = 1
    MATERIALIZED = 2
    CALLED_WITHOUT_ENGINE = 3
    ENGINE_ENABLED = 4


class AccelerationDomain:
    """A library's registry of functions that are candidates for acceleration."""

    def __init__(self, name: str, /, *, env_prefix: str | None = None):
        """Create a domain with the given unique ``name``."""
        if not isinstance(name, str):
            raise CoheriqDomainError("domain name must be a string")
        if not name:
            raise CoheriqDomainError("domain name cannot be empty")
        self._state = _DomainState.CONSTRUCTING
        self._name = name
        with _domain_registry_lock:
            if name in _domain_registry:
                raise CoheriqDomainError("domain name has already been used")
            _domain_registry[name] = self
        self._engine_registry: dict[str, AccelerationEngine] = {}
        self._dict: dict[str, Callable] = {}
        self._lock = Lock()
        self._impl: type | None = None
        self._base: type
        self._env_prefix = env_prefix

    def _ensure_realized_impl(self) -> None:
        """Set self._impl with the default implementation if not already set."""
        # Double-checked locking pattern
        if self._impl is not None:
            return
        with self._lock:
            if self._impl is not None:
                return
            if self._state != _DomainState.MATERIALIZED:
                raise CoheriqDomainError(
                    f"Expecting domain state to be MATERIALIZED, got {self._state}"
                )

            # Activate an engine if provided in an environment variable.
            # Otherwise, use default implementation.
            engine_name = (
                os.environ.get(f"{self._env_prefix}_ENGINE", "") if self._env_prefix else ""
            )
            if not engine_name:
                # Activate default implementation and return
                self._state = _DomainState.CALLED_WITHOUT_ENGINE
                self._impl = self._base
                return

        # Engine name was provided in an environment variable.  Activate engine
        # after releasing the lock, since it may involve loading imports.  The
        # import is function-local because ``activation`` imports this module;
        # confining it here keeps the module-level graph a one-way DAG and limits
        # the only domain -> activation reference to this env-var path.
        from .activation import enable_engine  # pylint: disable=cyclic-import

        enable_engine(self, engine_name)

    def acceleration_candidate(
        self, func: Callable | str | None = None, /, *, name: str | None = None
    ) -> Callable:
        """Mark ``func`` as a candidate for acceleration and return a dispatching wrapper."""
        # Do the right thing in the case where somebody passed the `name` in
        # place of `func`.
        if name is None and isinstance(func, str):
            name = func
            func = None

        def decorator(f) -> Callable:
            nonlocal name
            if name is None:
                name = f.__name__
            if not isinstance(name, str):
                raise CoheriqDomainError(
                    f"name must be None or a string, got {type(f).__name__} instead"
                )

            f_impl: Callable | None = None

            @functools.wraps(f)
            def wrapper(*args, **kwargs):
                nonlocal f_impl
                if f_impl is None:
                    self._ensure_realized_impl()
                    f_impl = getattr(self._impl, name)

                return f_impl(*args, **kwargs)

            with self._lock:
                if self._state != _DomainState.CONSTRUCTING:
                    raise CoheriqDomainError(
                        "Cannot mark a function after the domain is materialized"
                    )
                if TYPE_CHECKING and isclass(f):
                    # Usual use of this decorator replaces the class with a
                    # callable that wraps its constructor.  When type checking, it
                    # is preferable not to have this level of indirection, so we
                    # return the original class so type checking can succeed.
                    return f  # pragma: no cover
                self._dict[name] = f

            return wrapper

        if func is None:
            return decorator
        return decorator(func)

    def materialize(self) -> None:
        """Declare that the domain is complete.

        Acceleration candidates cannot be added after this has been called.
        """
        with self._lock:
            if self._state != _DomainState.CONSTRUCTING:
                raise CoheriqDomainError(
                    "Cannot materialize a domain that has already been materialized"
                )
            self._base = type(self._name, (), self._dict)
            self._state = _DomainState.MATERIALIZED
