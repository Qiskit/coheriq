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


import os, sys

def test_passes():
    assert 1 == 1

def test_fails():
    assert 2 + 2 == 5, "arithmetic is broken"

def test_crashes_hard():
    os._exit(1)            # would take down a shared-process runner

def test_segfault_like():
    import ctypes; ctypes.string_at(0)   # real segfault

def test_pollutes_global_state():
    # proves isolation: each test sees a pristine interpreter
    import builtins
    assert not hasattr(builtins, "_LEAKED")
    builtins._LEAKED = True
