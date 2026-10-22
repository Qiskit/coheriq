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

"""Exceptions raised by Coheriq."""


class CoheriqError(RuntimeError):
    """Base class for all Coheriq exceptions."""


class CoheriqLibraryError(CoheriqError):
    """Base class for errors caused by incorrect use of the Coheriq API by a library or engine."""


class CoheriqDomainError(CoheriqLibraryError):
    """Error caused by incorrect use of an :class:`.AccelerationDomain`."""


class CoheriqEngineError(CoheriqLibraryError):
    """Error caused by incorrect use of an :class:`.AccelerationEngine`."""


class CoheriqEngineInheritanceError(CoheriqEngineError):
    """Error caused by an invalid engine inheritance relationship."""


class CoheriqUserError(CoheriqError):
    """Error caused by incorrect use of coheriq by a user."""


class CoheriqDomainNotFoundError(CoheriqUserError):
    """Error caused by referencing a non-existent domain by name."""


class CoheriqEngineNotFoundError(CoheriqUserError):
    """Error caused by referencing a non-existent engine by name."""


class CoheriqTypeError(CoheriqUserError, TypeError):
    """Error caused by passing the wrong kind of object to a Coheriq API.

    Inherits from both :class:`CoheriqUserError` and the built-in
    :class:`TypeError`, so it is caught by ``except CoheriqError`` (or
    ``except CoheriqUserError``) as well as ``except TypeError``.
    """
