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

"""Tests for the ``coheriq_ragged_domain`` example.

These run against whichever implementation coheriq has active: the pure-Python
defaults, or an engine selected via the ``RAGGED_ENGINE`` environment variable.
The assertions are therefore written as **invariants** (properties true of any
correct softmax implementation) rather than exact-value comparisons, since
different engines need not be bit-identical.

Because the whole suite shares one process and one activation, these run
in-process (no ``--forked``); the ``ragged`` and ``ragged-engine`` tox
environments run this same file with and without the environment variable set.
"""

import math
import os

import pytest
from coheriq_ragged_domain import (
    RaggedBatch,
    ragged_batch_from_flat,
    segmented_softmax,
    segmented_topk_softmax,
)

# The backend the active implementation should report.  Derived from the same
# environment variable tox uses to select the engine, so a run cannot silently
# pass by exercising the wrong implementation.
EXPECTED_BACKEND = "fused" if os.environ.get("RAGGED_ENGINE") else "default"

# A batch with wildly varying row lengths, including an empty row and a
# length-1 row, plus a row with ties.
ROWS = [[2.0, 1.0, 0.1], [1.0], [3.0, 3.0, 0.0, 0.0], [], [5.0, -1.0]]
TOL = 1e-9


class TestContainer:
    def test_len(self):
        assert len(RaggedBatch(ROWS)) == len(ROWS)

    def test_row_lengths(self):
        assert RaggedBatch(ROWS).row_lengths() == [len(r) for r in ROWS]

    def test_getitem_values(self):
        batch = RaggedBatch(ROWS)
        for i, row in enumerate(ROWS):
            assert batch[i] == row

    def test_getitem_returns_independent_copy(self):
        batch = RaggedBatch(ROWS)
        row = batch[0]
        row[0] = 999.0
        # Mutating the returned row must not affect a fresh read of the batch.
        assert batch[0] != row
        assert batch[0] == ROWS[0]

    def test_getitem_distinct_objects(self):
        batch = RaggedBatch(ROWS)
        assert batch[0] is not batch[0]

    def test_iter_matches_getitem(self):
        batch = RaggedBatch(ROWS)
        assert list(batch) == [batch[i] for i in range(len(batch))]

    def test_from_flat_roundtrip(self):
        batch = RaggedBatch(ROWS)
        rebuilt = ragged_batch_from_flat(batch._values, batch._offsets)
        assert rebuilt.row_lengths() == batch.row_lengths()
        assert list(rebuilt) == list(batch)

    def test_repr_contains_row_count(self):
        assert "5 rows" in repr(RaggedBatch(ROWS))

    def test_empty_batch(self):
        batch = RaggedBatch([])
        assert len(batch) == 0
        assert batch.row_lengths() == []


class TestSegmentedSoftmax:
    def test_shape_preserved(self):
        batch = RaggedBatch(ROWS)
        out = segmented_softmax(batch)
        assert len(out) == len(batch)
        assert out.row_lengths() == batch.row_lengths()

    def test_rows_are_probability_distributions(self):
        out = segmented_softmax(RaggedBatch(ROWS))
        for i in range(len(out)):
            row = out[i]
            if row:
                assert abs(sum(row) - 1.0) < TOL
            assert all(-TOL <= p <= 1.0 + TOL for p in row)

    def test_empty_row_stays_empty(self):
        out = segmented_softmax(RaggedBatch(ROWS))
        # ROWS[3] is the empty row.
        assert out[3] == []

    def test_matches_reference_softmax(self):
        # Invariant against an independent stable-softmax reference (not against
        # another engine): the numbers must be a correct softmax regardless of
        # which implementation produced them.
        out = segmented_softmax(RaggedBatch(ROWS))
        for i, row in enumerate(ROWS):
            if not row:
                continue
            m = max(row)
            exps = [math.exp(x - m) for x in row]
            total = sum(exps)
            reference = [e / total for e in exps]
            for got, want in zip(out[i], reference):
                assert abs(got - want) < TOL


class TestSegmentedTopkSoftmax:
    @pytest.mark.parametrize("k", [1, 2, 3])
    def test_row_length_is_min_k_rowlen(self, k):
        batch = RaggedBatch(ROWS)
        out = segmented_topk_softmax(batch, k)
        for i, row in enumerate(ROWS):
            assert len(out[i]) == min(k, len(row))

    def test_indices_unique_and_in_range(self):
        out = segmented_topk_softmax(RaggedBatch(ROWS), k=2)
        for i, row in enumerate(ROWS):
            idxs = [idx for idx, _ in out[i]]
            assert len(set(idxs)) == len(idxs)
            assert all(0 <= idx < len(row) for idx in idxs)

    def test_kept_probs_sum_to_one(self):
        out = segmented_topk_softmax(RaggedBatch(ROWS), k=2)
        for row in out:
            probs = [p for _, p in row]
            if probs:
                assert abs(sum(probs) - 1.0) < TOL

    def test_selects_the_largest_values(self):
        # Top-1 must pick the argmax of each non-empty row.
        out = segmented_topk_softmax(RaggedBatch(ROWS), k=1)
        for i, row in enumerate(ROWS):
            if not row:
                continue
            (idx, prob) = out[i][0]
            assert row[idx] == max(row)
            assert abs(prob - 1.0) < TOL


class TestActiveBackend:
    """Prove which implementation the run is exercising."""

    def test_container_backend(self):
        assert RaggedBatch(ROWS).backend == EXPECTED_BACKEND

    def test_result_backend(self):
        out = segmented_softmax(RaggedBatch([[1.0, 2.0]]))
        assert out.backend == EXPECTED_BACKEND
