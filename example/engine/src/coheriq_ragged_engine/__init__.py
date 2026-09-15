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

"""A "fused" acceleration engine for the ``coheriq_ragged_domain`` example.

This package plays the role of the *engine* in the coheriq three-party model.
It provides alternative implementations of the domain's candidates.

The engine's overrides live in the :mod:`coheriq_ragged_engine._overrides`
submodule, which is declared as an entry point under the
``coheriq.engines.ragged`` group.  coheriq loads that submodule on demand when
user code calls ``coheriq.enable_engine("ragged", "fused")``.

Keeping the engine out of this ``__init__`` is deliberate: importing the package
should not register the engine as a side effect.  A real package might ship
other, unrelated things alongside the engine, and importing them should not
enable acceleration.
"""

from __future__ import annotations
