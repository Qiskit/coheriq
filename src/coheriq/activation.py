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

"""Contains the code to activate an acceleration engine."""

from __future__ import annotations

from importlib.metadata import entry_points

from .domain import REFERENCE, AccelerationDomain, _DomainState, _get_domain_by_name
from .engine import AccelerationEngine, _EngineState
from .exceptions import (
    CoheriqDomainError,
    CoheriqDomainNotFoundError,
    CoheriqEngineError,
    CoheriqEngineNotFoundError,
)


def _resolve_domain(domain: str | AccelerationDomain, /) -> AccelerationDomain:
    """Return ``domain`` itself, or the registered domain with that name."""
    if not isinstance(domain, str):
        return domain
    try:
        return _get_domain_by_name(domain)
    except KeyError:
        raise CoheriqDomainNotFoundError(
            f"No domain named '{domain}' has been registered"
        ) from None


def enable_engine(domain: str | AccelerationDomain, engine: str | AccelerationEngine, /) -> None:
    """Activate ``engine`` for ``domain`` so its overrides take priority over the defaults.

    ``domain`` may be an :class:`.AccelerationDomain` or the name of one; ``engine``
    may be an :class:`.AccelerationEngine` or the name of one.  Enabling an engine
    that is already active is an idempotent no-op.
    """
    domain_ = _resolve_domain(domain)

    # Load a plugin if relevant
    if isinstance(engine, str):
        discovered_plugins = entry_points(group=f"coheriq.engines.{domain_._name}")
        try:
            plugin = discovered_plugins[engine]
        except KeyError:
            pass
        else:
            plugin.load()

    # To avoid deadlock, all locks must be acquired in the same order
    # within all code paths that acquire both simultaneously.  The
    # convention we have adopted is to always acquire the *domain* lock
    # *first*, and any engine lock second.
    with domain_._lock:
        if isinstance(engine, str):
            try:
                engine_ = domain_._engine_registry[engine]
            except KeyError:
                raise CoheriqEngineNotFoundError(
                    f"Cannot find engine with name '{engine}' in domain '{domain_._name}'"
                ) from None
        else:
            engine_ = engine

        _enable_engine_low_level(domain_, engine_)


def _enable_engine_low_level(domain: AccelerationDomain, engine: AccelerationEngine) -> None:
    """Enable engine for domain.

    This assumes the locks for ``domain`` and ``engine`` have already been
    acquired (in that order).  The user-facing function is :func:`enable_engine`.
    """
    if engine._state == _EngineState.ENABLED:
        # This engine is already enabled.  Enabling the same engine
        # twice is treated as an idempotent operation, as it
        # benefits usability and there is not a good motivation to
        # treat it as an error condition.
        return
    if domain._state != _DomainState.MATERIALIZED:
        raise CoheriqDomainError(f"Cannot enable an engine if domain is in state {domain._state}")
    if engine._state != _EngineState.MATERIALIZED:
        raise CoheriqEngineError(f"Expecting engine state to be MATERIALIZED, got {engine._state}")

    engine._state = _EngineState.ENABLED
    domain._state = _DomainState.ENGINE_ENABLED
    domain._impl = engine._impl


def available_engines(domain: str | AccelerationDomain, /) -> tuple[str, ...]:
    """Return the names of the engines that can be enabled for ``domain``, sorted.

    ``domain`` may be an :class:`.AccelerationDomain` or the name of one.

    This reports both engines that have already been registered (because their
    module has been imported) and engines advertised through the
    ``coheriq.engines.<domain>`` entry point group but not yet imported, since
    :func:`enable_engine` accepts either.  Advertised plugins are *not* imported
    in order to answer this question, so a name being listed means that
    :func:`enable_engine` will attempt it, not that it is guaranteed to load.

    Unlike calling an acceleration candidate, this
    does not resolve or freeze the implementation: an engine can still be
    enabled afterwards.
    """
    domain_ = _resolve_domain(domain)
    with domain_._lock:
        names = set(domain_._engine_registry)
    # Engines advertised via entry points may not have been imported yet, in
    # which case they are absent from the registry above but are still valid
    # arguments to enable_engine(), which loads the plugin on demand.
    names.update(ep.name for ep in entry_points(group=f"coheriq.engines.{domain_._name}"))
    return tuple(sorted(names))


def active_implementation(domain: str | AccelerationDomain, /) -> str | None:
    """Return the name of the implementation ``domain`` has resolved to, or ``None``.

    ``domain`` may be an :class:`.AccelerationDomain` or the name of one.

    There are three possible results:

    * ``None`` -- the domain has not resolved an implementation yet, so an engine
      can still be enabled.
    * :data:`~coheriq.REFERENCE` (the string ``"reference"``) -- the domain has
      resolved to its own reference implementation.  No engine is active, and it
      is too late to enable one.
    * any other string -- the name of the engine that is active.

    ``None`` therefore means "not decided yet", and never "decided on no engine";
    the latter is reported as :data:`~coheriq.REFERENCE`.  Because
    ``"reference"`` is a possible result, it cannot also be an engine name, and
    :class:`.AccelerationEngine` rejects it.

    Unlike calling an acceleration candidate, this does not resolve or freeze the
    implementation.  Asking what is active never commits the domain to an answer,
    so a ``None`` result does not become stale merely by being observed.
    """
    domain_ = _resolve_domain(domain)
    with domain_._lock:
        if domain_._state in (_DomainState.CONSTRUCTING, _DomainState.MATERIALIZED):
            return None
        if domain_._state == _DomainState.CALLED_WITHOUT_ENGINE:
            return REFERENCE
        for name, engine in domain_._engine_registry.items():
            if engine._state == _EngineState.ENABLED:
                return name
        # Unreachable: ENGINE_ENABLED is only set by _enable_engine_low_level,
        # which marks the engine ENABLED at the same time, under this lock.
        raise CoheriqDomainError(  # pragma: no cover
            f"Domain '{domain_._name}' is in state {domain_._state} but no engine is enabled"
        )
