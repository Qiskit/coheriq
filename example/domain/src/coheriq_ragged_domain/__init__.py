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

"""A tiny example library that adopts coheriq.

This package plays the role of the *domain* in the coheriq three-party model: a
library that marks some of its data structures and functions as candidates for
acceleration.  It works perfectly well on its own, in pure Python.  A separate
*engine* package (``coheriq_ragged_engine``) can later be activated to swap in
faster implementations without any change to calling code.

The computation is a **segmented softmax** over a *ragged* batch of rows (rows
of differing lengths).  Raggedness is what makes this awkward for a rectangular
array library like NumPy, and therefore a natural thing to hand off to a
purpose-built backend.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

from coheriq import AccelerationDomain

_domain = AccelerationDomain("ragged", env_prefix="RAGGED")

# The library marks its candidates below; user code activates an engine with
# coheriq's own function -- there is nothing for this package to re-export:
#   coheriq.enable_engine("ragged", "fused")


@_domain.acceleration_candidate
class RaggedBatch:
    """A batch of variable-length numeric rows.

    Internally the rows are stored in a single flat ``values`` buffer together
    with an ``offsets`` array (CSR-style): row ``i`` is
    ``values[offsets[i]:offsets[i + 1]]``.  This contiguous layout is exactly
    what a compiled backend wants; here it is an internal implementation detail.

    The public API deliberately hands out **copies** rather than views (see
    :meth:`__getitem__`).  This keeps the Python contract identical to a future
    compiled engine, which cannot safely hand out borrowed pointers into its own
    storage, so calling code never grows a dependency on aliasing.
    """

    def __init__(self, rows: Iterable[Iterable[float]]):
        """Build a batch from an iterable of rows (an iterable of floats each)."""
        values: list[float] = []
        offsets: list[int] = [0]
        for row in rows:
            values.extend(float(x) for x in row)
            offsets.append(len(values))
        self._values = values
        self._offsets = offsets

    @property
    def backend(self) -> str:
        """Name of the implementation backing this object (``"default"`` here)."""
        return "default"

    def __len__(self) -> int:
        """Return the number of rows."""
        return len(self._offsets) - 1

    def __getitem__(self, i: int) -> list[float]:
        """Return row ``i`` as a fresh ``list`` -- an independent copy, never a view.

        Callers get value semantics: mutating or holding the returned row never
        touches the batch, and holding a row does not keep the batch alive.  A
        backend that wanted zero-copy access would expose it as a separate,
        explicitly named accessor with documented lifetime rules -- not by
        changing what ``[]`` means.
        """
        start, stop = self._offsets[i], self._offsets[i + 1]
        return list(self._values[start:stop])

    def __iter__(self):
        """Iterate over the rows, each yielded as a copied ``list``."""
        for i in range(len(self)):
            yield self[i]

    def row_lengths(self) -> list[int]:
        """Return the length of each row."""
        return [self._offsets[i + 1] - self._offsets[i] for i in range(len(self))]

    def __repr__(self) -> str:
        """Return a short representation naming the active backend."""
        return f"RaggedBatch({len(self)} rows, {self.backend} backend)"


@_domain.acceleration_candidate
def ragged_batch_from_flat(values: Sequence[float], offsets: Sequence[int]) -> RaggedBatch:
    """Build a :class:`RaggedBatch` from a flat ``values`` buffer and ``offsets``.

    This is the "internal truth" constructor -- it exposes the contiguous layout
    the container uses under the hood.  It is a free function rather than a method
    so that, like the other operations here, an engine can override it to build
    its own container type.  Row ``i`` is ``values[offsets[i]:offsets[i + 1]]``.
    """
    rows = [list(values[offsets[i] : offsets[i + 1]]) for i in range(len(offsets) - 1)]
    return RaggedBatch(rows)


@_domain.acceleration_candidate
def segmented_softmax(batch: RaggedBatch) -> RaggedBatch:
    """Return a new batch holding the per-row softmax of ``batch``.

    The default implementation is the obvious, readable version: for each row it
    makes several passes -- find the max (for numerical stability), subtract and
    exponentiate, sum, then divide.  Each row is materialized as a Python list
    along the way.
    """
    result_rows: list[list[float]] = []
    for row in batch:
        if not row:
            result_rows.append([])
            continue
        m = max(row)
        exps = [math.exp(x - m) for x in row]
        total = sum(exps)
        result_rows.append([e / total for e in exps])
    return RaggedBatch(result_rows)


@_domain.acceleration_candidate
def segmented_topk_softmax(batch: RaggedBatch, k: int) -> list[list[tuple[int, float]]]:
    """Return, per row, the top-``k`` entries as ``(index, probability)`` pairs.

    The probabilities are a softmax computed over only the selected top-``k``
    values, so each returned row sums to 1.  Indices refer back into the
    original row.  The default implementation sorts the whole row to find the
    top ``k`` (``O(n log n)``); a backend can select in ``O(n)`` instead.
    """
    result: list[list[tuple[int, float]]] = []
    for row in batch:
        if not row:
            result.append([])
            continue
        ranked = sorted(enumerate(row), key=lambda pair: pair[1], reverse=True)
        topk = ranked[:k]
        m = max(v for _, v in topk)
        exps = [(i, math.exp(v - m)) for i, v in topk]
        total = sum(e for _, e in exps)
        result.append([(i, e / total) for i, e in exps])
    return result


_domain.materialize()

__all__ = [
    "RaggedBatch",
    "ragged_batch_from_flat",
    "segmented_softmax",
    "segmented_topk_softmax",
]
