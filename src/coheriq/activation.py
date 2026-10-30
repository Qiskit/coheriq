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

    Passing :data:`~coheriq.REFERENCE` selects the domain's own reference
    implementation.  That is worth doing explicitly even though it is what happens
    by default, because an explicit call takes precedence over the domain's
    environment variable: it pins the reference implementation regardless of the
    surrounding environment, which silence cannot do.
    """
    domain_ = _resolve_domain(domain)

    if engine == REFERENCE:
        # The reference implementation is the one engine a domain always has, and
        # it has no registry entry because the domain builds it rather than an
        # AccelerationEngine registering it.  Pinning it is a forward transition
        # into the same settled state a first call would reach, so it goes through
        # the ordinary freeze rather than a path of its own.
        with domain_._lock:
            _enable_reference_low_level(domain_)
        return

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

        with engine_._lock:
            _enable_engine_low_level(domain_, engine_)


def _enable_engine_low_level(domain: AccelerationDomain, engine: AccelerationEngine) -> None:
    """Enable engine for domain.

    This assumes the locks for ``domain`` and ``engine`` have already been
    acquired (in that order), as it mutates state on both.  The user-facing
    function is :func:`enable_engine`.
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


def _enable_reference_low_level(domain: AccelerationDomain) -> None:
    """Pin ``domain`` to its own reference implementation.

    This assumes ``domain``'s lock has already been acquired.  The user-facing
    entry point is ``enable_engine(domain, REFERENCE)``.
    """
    if domain._state == _DomainState.CALLED_WITHOUT_ENGINE:
        # Already settled on the reference implementation.  Treated as an
        # idempotent no-op, matching enable_engine() on an already-active engine.
        return
    if domain._state != _DomainState.MATERIALIZED:
        raise CoheriqDomainError(
            f"Cannot enable the reference implementation if domain is in state {domain._state}"
        )
    domain._state = _DomainState.CALLED_WITHOUT_ENGINE
    domain._impl = domain._base


def available_engines(domain: str | AccelerationDomain, /) -> tuple[str, ...]:
    """Return the names of the engines that can be enabled for ``domain``, sorted.

    ``domain`` may be an :class:`.AccelerationDomain` or the name of one.

    Every name returned is a valid argument to :func:`enable_engine`.  The result
    always includes :data:`~coheriq.REFERENCE`, the domain's own reference
    implementation, which is listed first; the remaining engines follow in
    alphabetical order.  Because the reference implementation is always present,
    the result is never empty, and its length is therefore not a count of the
    accelerators installed.

    Besides the reference implementation, this reports both engines that have
    already been registered (because their module has been imported) and engines
    advertised through the ``coheriq.engines.<domain>`` entry point group but not
    yet imported, since :func:`enable_engine` accepts either.  Advertised plugins
    are *not* imported in order to answer this question, so a name being listed
    means that :func:`enable_engine` will attempt it, not that it is guaranteed to
    load.

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
    # The reference implementation leads the list because it is the one engine
    # every domain has and the one in effect until another is enabled.  A future
    # priority mechanism would order the rest around it rather than after it.
    names.discard(REFERENCE)
    return (REFERENCE, *sorted(names))


def active_engine(domain: str | AccelerationDomain, /) -> str | None:
    """Return the name of the engine ``domain`` has resolved to, or ``None``.

    ``domain`` may be an :class:`.AccelerationDomain` or the name of one.

    There are three possible results:

    * ``None`` -- the domain has not resolved an engine yet, so a different one
      can still be enabled.
    * :data:`~coheriq.REFERENCE` (the string ``"reference"``) -- the domain has
      resolved to its own reference implementation.  It is too late to enable a
      different engine.
    * any other non-empty string -- the name of the engine that is active.

    ``None`` therefore means "not decided yet", while :data:`~coheriq.REFERENCE`
    means "decided on the reference implementation".

    Unlike calling an acceleration candidate, this does not resolve or freeze the
    implementation.
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
