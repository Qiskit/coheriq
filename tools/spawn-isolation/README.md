# Spawn-based per-test isolation (prototype, not wired into CI)

Exploratory. Nothing here runs as part of `tox`; it is parked so the
investigation does not have to be redone.

## What this is

`pytest_isolate_spawn.py` runs each test in a **freshly spawned interpreter**
instead of a forked one, by overriding `pytest_runtest_protocol` to invoke
`python -m pytest <nodeid>` as a subprocess. No `os.fork()`, so it works on
Windows.

Reports cross the process boundary as a JSON sidecar written by the child.
That is the point: `pytest-forked` marshals pytest's own report objects, which
is what breaks on new pytest versions.

## Why this was investigated

The requirement in this repo is not "fork". It is "a process where the
domain/engine registry is empty". A spawned interpreter satisfies that by
construction, where a fork only satisfies it as long as the parent has not
touched the registry first.

Two constraints motivated the look:

- `pytest --forked` needs `os.fork()`, so the `py` and `doctest` tox envs skip
  Windows (see the matrix in `.github/workflows/test_latest_versions.yml`).
- `pytest-forked` was dormant 2023-2026 and this repo vendors a patched copy
  (`test/coverage_startup/pytest_forked.py`, ~320 lines). pytest 9.2 moved
  `report.nodeid` behind a dataclass its `marshal` transport cannot serialize,
  which is why `pyproject.toml` pins `pytest<9.2` (commit e21e0ba).

## Status: deliberately not adopted

`--forked` works on the platforms this repo tests, and Windows already gets
real dispatch coverage through the in-process `notebook`/`ragged` envs. The
trigger to revisit is the pytest pin, not Windows support.

## Measurements

26 tests, Linux, Python 3.14:

| approach            | wall time |
| ------------------- | --------- |
| `--forked`          | 0.2s      |
| spawn, serial       | 4.5s      |
| spawn, 8 concurrent | 0.79s     |
| spawn, 16 concurrent| 0.53s     |

About 0.17s per test, dominated by `import pytest` (0.114s). Embarrassingly
parallel, so pairing this with `pytest-xdist` hides most of it. The constant
scales with import cost, so a Qiskit-sized import was **not** measured and is
the number to check before trusting this elsewhere.

## The trap worth remembering

The first version of this plugin reported a segfaulting test as **nothing** --
a silent pass. A child killed by a signal writes no report, and absence read as
success.

The fix is in `pytest_runtest_protocol`: a missing `call` phase is treated as a
failure, not as silence. **Any** process-isolation scheme has this failure mode.
Any real version of this needs a test asserting that a segfault reports as a
failure.

## Verified

Against `test/` on pytest 9.2.0 -- the version that breaks `pytest-forked`:

    pip install pytest-xdist          # optional, for -n
    PYTHONPATH=tools/spawn-isolation \
      python -m pytest -p pytest_isolate_spawn --isolate -q test/

26 passed. The `demo/` directory exercises the reporting edge cases: a plain
failure, `os._exit(1)`, a real segfault via `ctypes.string_at(0)`, and a test
that sets a `builtins` global to prove state does not leak between tests.
All report correctly and the parent run survives.

## Not addressed

- **Coverage.** The `--forked` envs rely on the vendored shim's explicit
  coverage flush. Spawn needs subprocess coverage plus `coverage combine`.
- **Windows actually run.** The code path uses no POSIX-only calls, which is
  not the same as having been tested on Windows.
- **MPI.** Irrelevant here, but noted for the sibling case: under
  `mpirun -n N pytest`, MPI owns the process topology and pytest runs inside
  it. A per-test spawn from inside a rank is not a rank -- `COMM_WORLD` is
  size 1 and collectives hang or silently test nothing. The two designs cannot
  both own process creation; a real plugin should hard-error on
  `--isolate` combined with `--only-mpi` rather than fail subtly.
