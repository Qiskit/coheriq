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

"""The "fused" acceleration engine: a genuine C++/nanobind backend.

Entry-point target for ``coheriq.engines.ragged:fused``.  On import it registers
the compiled container and operations with coheriq, then materializes the engine.
The heavy lifting lives in the compiled :mod:`coheriq_ragged_engine._ragged_ext`
extension; this module only wires it into coheriq.

Kept out of the package ``__init__`` so that importing ``coheriq_ragged_engine``
has no side effect -- only loading this entry-point module registers the engine,
and only when coheriq loads it via ``coheriq.enable_engine("ragged", "fused")``
(or the ``RAGGED_ENGINE`` environment variable).
"""

from __future__ import annotations

# Importing the domain guarantees it is registered and materialized before we
# construct the engine below (the engine looks the domain up by name).
import coheriq_ragged_domain  # noqa: F401  pylint: disable=unused-import
from coheriq import AccelerationEngine

from ._ragged_ext import (
    RaggedBatch,
    ragged_batch_from_flat,
    segmented_softmax,
    segmented_topk_softmax,
)

_engine = AccelerationEngine("ragged", "fused")

_engine.override(RaggedBatch)
_engine.override(ragged_batch_from_flat)
_engine.override(segmented_softmax)
_engine.override(segmented_topk_softmax)

_engine.materialize()
