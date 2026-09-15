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

from .domain import AccelerationDomain, _DomainState, _get_domain_by_name
from .engine import AccelerationEngine, _EngineState
from .exceptions import (
    CoheriqDomainError,
    CoheriqDomainNotFoundError,
    CoheriqEngineError,
    CoheriqEngineNotFoundError,
)


def enable_engine(domain: str | AccelerationDomain, engine: str | AccelerationEngine, /) -> None:
    """Activate ``engine`` for ``domain`` so its overrides take priority over the defaults.

    ``domain`` may be an :class:`.AccelerationDomain` or the name of one; ``engine``
    may be an :class:`.AccelerationEngine` or the name of one.  Enabling an engine
    that is already active is an idempotent no-op.
    """
    if isinstance(domain, str):
        try:
            domain_ = _get_domain_by_name(domain)
        except KeyError:
            raise CoheriqDomainNotFoundError(
                f"No domain named '{domain}' has been registered"
            ) from None
    else:
        domain_ = domain

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
