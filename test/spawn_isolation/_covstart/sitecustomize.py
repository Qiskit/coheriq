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


"""Start coverage in a spawned child.

`process_startup()` returns immediately unless COVERAGE_PROCESS_START is set,
so this file is harmless on sys.path when coverage is not in use.
"""

try:
    import coverage
except ImportError:
    pass
else:
    coverage.process_startup()
