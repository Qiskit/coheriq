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
from .domain import AccelerationDomain
from .engine import AccelerationEngine
from .exceptions import (
    CoheriqDomainError,
    CoheriqDomainNotFoundError,
    CoheriqEngineError,
    CoheriqEngineInheritanceError,
    CoheriqEngineNotFoundError,
    CoheriqError,
    CoheriqLibraryError,
    CoheriqUserError,
)

__all__ = [
    "AccelerationDomain",
    "AccelerationEngine",
    "CoheriqDomainError",
    "CoheriqDomainNotFoundError",
    "CoheriqEngineError",
    "CoheriqEngineInheritanceError",
    "CoheriqEngineNotFoundError",
    "CoheriqError",
    "CoheriqLibraryError",
    "CoheriqUserError",
    "active_engine",
    "available_engines",
    "enable_engine",
]
