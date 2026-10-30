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
import importlib.util
import os
import sys
import warnings
from collections.abc import Callable
from enum import Enum
from inspect import isclass
from threading import Lock
from types import ModuleType
from typing import TYPE_CHECKING, Final

from .exceptions import (
    CoheriqDomainError,
    CoheriqDomainWarning,
    CoheriqError,
)

if TYPE_CHECKING:
    from .engine import AccelerationEngine

_domain_registry_lock = Lock()
_domain_registry: dict[str, AccelerationDomain] = {}

REFERENCE: Final = "reference"
"""The name of a domain's own reference implementation.

Every domain has this engine: it is the one built from the implementations the
domain itself declares, and is the one that goes into effect unless another is enabled.  Pass it
to :func:`~coheriq.enable_engine` to select it explicitly, and
:func:`~coheriq.active_engine` reports it when it is active.

It is listed by :func:`~coheriq.available_engines` like any other engine, so it
is a name the domain owns: :class:`~coheriq.AccelerationEngine` cannot be
constructed with it.  The whole ``"reference"`` prefix is reserved the same way,
against a possible future design in which a domain versions its reference
implementation.
"""

_RESERVED_ENGINE_NAME_PREFIX: Final = REFERENCE


def _module_is_findable(name: str) -> bool:
    """Return whether ``name`` names a module that can be found on the import path.

    This never imports ``name``: an already-imported module is answered from
    ``sys.modules``, and anything else is resolved by the finders alone.

    The broad ``except`` is deliberate.  ``find_spec`` raises rather than
    returning ``None`` for a dotted name whose parent cannot be imported, and a
    third-party finder may raise anything at all.  Since the result only ever
    informs a warning, nothing here may break domain construction.
    """
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:  # pylint: disable=broad-exception-caught
        return False


def _warn_if_name_is_not_a_module(name: str) -> None:
    """Warn if ``name`` does not name an importable module.

    A domain's name should be the ``__name__`` of the package it belongs to, so
    that users can pass the module itself wherever a domain is expected.  This
    is a convention rather than a requirement: it is only ever a warning, since
    a domain defined in a script, a notebook, or a test has no package to name.
    """
    if _module_is_findable(name):
        return
    warnings.warn(
        f"Domain name '{name}' does not name an importable module.  A domain's "
        f"name should be the __name__ of the package it belongs to, which lets "
        f"users pass that module to coheriq.enable_engine() instead of repeating "
        f"its name as a string.",
        CoheriqDomainWarning,
        stacklevel=3,
    )


def _domain_name_from_module(module: ModuleType, /) -> str:
    """Return the domain name a module stands in for.

    Resolution is by name: the convention is that a domain is named after the
    package it belongs to, so the module's ``__name__`` is the lookup key.  No
    separate record of which module defined a domain is kept, which keeps the
    convention the single source of truth.
    """
    return module.__name__


def _domain_name_of(domain: str | ModuleType | AccelerationDomain, /) -> str | None:
    """Return the name ``domain`` refers to, or ``None`` if it names nothing."""
    if isinstance(domain, AccelerationDomain):
        return domain._name
    if isinstance(domain, ModuleType):
        return _domain_name_from_module(domain)
    if isinstance(domain, str):
        return domain
    return None


def _domain_not_found_message(name: str) -> str:
    """Explain that no domain named ``name`` is registered, and suggest why.

    A domain is registered as a side effect of importing the library that
    defines it, so the overwhelmingly likely cause is that the library has not
    been imported yet.  Checking whether the name is importable distinguishes
    that from a misspelling, which otherwise produce the same bare message.
    """
    message = f"No domain named '{name}' has been registered"
    if name in sys.modules:
        return f"{message}.  Module '{name}' is imported but defines no domain of that name."
    if _module_is_findable(name):
        return (
            f"{message}.  A module named '{name}' is installed but has not been "
            f"imported, and importing it is what registers the domain.  Import "
            f"it first, and consider passing the module itself instead of its "
            f"name, which makes the ordering impossible to get wrong."
        )
    registered = known_domains()
    if registered:
        return f"{message}.  Registered domains: {', '.join(registered)}"
    return (
        f"{message}, and no domains are registered at all.  A domain is "
        f"registered by importing the library that defines it, so the library "
        f"this name refers to has probably not been imported yet."
    )


def _resolve_domain(
    domain: str | ModuleType | AccelerationDomain,
    not_found: type[CoheriqError],
    /,
) -> tuple[AccelerationDomain, str]:
    """Return the domain ``domain`` refers to, with the name it was found under.

    ``domain`` may be an :class:`.AccelerationDomain`, the name of one, or the
    module a domain is named after.  Accepting the module is what makes the
    import-order requirement unstatable: a module cannot be passed without
    having been imported, and importing it is what registers the domain.

    ``not_found`` is the exception raised when nothing is registered under the
    name.  Callers supply it because they classify the same mistake
    differently: a user naming a missing domain has made a
    :class:`~coheriq.CoheriqUserError`, while an engine doing so has made a
    :class:`~coheriq.CoheriqLibraryError`.  An argument that cannot name a
    domain at all is a :exc:`TypeError` regardless of caller.
    """
    name = _domain_name_of(domain)
    if name is None:
        raise TypeError(
            f"domain must be an AccelerationDomain, a module, or the name of a "
            f"domain, got {type(domain).__name__} instead"
        )
    if isinstance(domain, AccelerationDomain):
        # Already the object, so no lookup and no way for it to be missing.
        return domain, name
    try:
        return _get_domain_by_name(name), name
    except KeyError:
        raise not_found(_domain_not_found_message(name)) from None


def _get_domain_by_name(name: str) -> AccelerationDomain:
    """Return the domain with the given name; raises KeyError if not found."""
    with _domain_registry_lock:
        return _domain_registry[name]


def known_domains() -> tuple[str, ...]:
    """Return domains known to the current process.

    Only domains that have been constructed in the current process are
    reported. This does not include installed domains from packages that
    have not yet been imported.
    """
    with _domain_registry_lock:
        return tuple(sorted(_domain_registry.keys()))


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
        _warn_if_name_is_not_a_module(name)
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
