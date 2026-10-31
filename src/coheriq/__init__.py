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

"""Coheriq: a dispatch decorator framework for runtime acceleration of library functions."""

from __future__ import annotations

from .activation import active_engine, available_engines, enable_engine
from .domain import REFERENCE, AccelerationDomain, known_domains, resolve_impl
from .engine import AccelerationEngine
from .exceptions import (
    CoheriqDomainError,
    CoheriqDomainNotFoundError,
    CoheriqDomainWarning,
    CoheriqEngineError,
    CoheriqEngineInheritanceError,
    CoheriqEngineNotFoundError,
    CoheriqError,
    CoheriqLibraryError,
    CoheriqTypeError,
    CoheriqUserError,
    CoheriqWarning,
)

__all__ = [
    "REFERENCE",
    "AccelerationDomain",
    "AccelerationEngine",
    "CoheriqDomainError",
    "CoheriqDomainNotFoundError",
    "CoheriqDomainWarning",
    "CoheriqEngineError",
    "CoheriqEngineInheritanceError",
    "CoheriqEngineNotFoundError",
    "CoheriqError",
    "CoheriqLibraryError",
    "CoheriqTypeError",
    "CoheriqUserError",
    "CoheriqWarning",
    "active_engine",
    "available_engines",
    "enable_engine",
    "known_domains",
    "resolve_impl",
]
