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

"""Type-checker assertions for the decorators' declared signatures.

Checked by ``mypy``, never run by ``pytest``; see ``README.md`` in this directory.
"""

from __future__ import annotations

from collections.abc import Callable

from coheriq import AccelerationDomain, AccelerationEngine

_domain = AccelerationDomain("check_decorators")


# --- acceleration_candidate preserves the signature ---------------------------
#
# Annotated assignment is the instrument here: it checks structurally, so a
# wrong signature is an assignment error.  assert_type cannot be used, as it
# compares nominally and a decorated function is not the same *type* as the
# Callable it is assignable to.


@_domain.acceleration_candidate
def normalize(xs: list[float]) -> list[float]:
    return xs


_normalize_sig: Callable[[list[float]], list[float]] = normalize


@_domain.acceleration_candidate("positional_name")
def scale(xs: list[float], k: float) -> list[float]:
    return xs


_scale_sig: Callable[[list[float], float], list[float]] = scale


@_domain.acceleration_candidate(name="keyword_name")
def shift(xs: list[float], k: float) -> list[float]:
    return xs


_shift_sig: Callable[[list[float], float], list[float]] = shift


# A marked class keeps its type, by way of the isclass() bypass in the decorator.
@_domain.acceleration_candidate
class Container:
    def __init__(self, n: int) -> None:
        self.n = n


_container_sig: Callable[[int], Container] = Container


# --- the signature is really checked, not merely present ----------------------
#
# Each of these is the error py.typed exists to surface.  They are spelled as
# ignores so that mypy's warn_unused_ignores reports them if they stop failing.

_bad_arg = normalize("not a list")  # type: ignore[arg-type]
_bad_return: int = normalize([1.0])  # type: ignore[assignment]
_bad_arity = normalize([1.0], 2.0)  # type: ignore[call-arg]


# --- the name forms are mutually exclusive ------------------------------------
#
# Passing a name both positionally and as a keyword is rejected.  At runtime
# the positional string is taken as the object to decorate, so the string
# itself is marked as the candidate while the keyword is the name registered;
# override raises TypeError instead.
#
# Written as a decorator application rather than a bare call: a bare call
# matches the first overload with _F left unsolved and so is accepted, and only
# applying the result forces mypy to choose a factory overload.
@_domain.acceleration_candidate("positional", name="keyword")  # type: ignore[call-overload]
def _both(xs: list[float]) -> list[float]:
    return xs


# The no-argument form is accepted.  It is redundant rather than wrong -- the
# decorator falls back to __name__ either way -- and @decorator() is a common
# enough reflex that rejecting it would buy nothing.  Allowing it is also the
# reversible choice: loosening a signature is never a breaking change, so this
# can be revisited before 1.0.
@_domain.acceleration_candidate()
def _no_args(xs: list[float]) -> list[float]:
    return xs


_no_args_sig: Callable[[list[float]], list[float]] = _no_args


_domain.materialize()


# --- override preserves the signature the same way ----------------------------

_engine = AccelerationEngine("check_decorators", "check_engine")


@_engine.override
def normalize_override(xs: list[float]) -> list[float]:
    return xs


_override_sig: Callable[[list[float]], list[float]] = normalize_override


@_engine.override("positional_name")
def scale_override(xs: list[float], k: float) -> list[float]:
    return xs


_scale_override_sig: Callable[[list[float], float], list[float]] = scale_override


@_engine.override(name="keyword_name")
def shift_override(xs: list[float], k: float) -> list[float]:
    return xs


_shift_override_sig: Callable[[list[float], float], list[float]] = shift_override


_override_bad_arg = normalize_override("not a list")  # type: ignore[arg-type]
_override_bad_return: int = normalize_override([1.0])  # type: ignore[assignment]


@_engine.override("positional", name="keyword")  # type: ignore[call-overload]
def _override_both(xs: list[float]) -> list[float]:
    return xs


# The no-argument form is accepted here too, for the same reason.
@_engine.override()
def _override_no_args(xs: list[float]) -> list[float]:
    return xs
