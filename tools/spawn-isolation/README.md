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

## Coverage: works, but needs three things

Measured: **81%, byte-identical to the `--forked` baseline** -- same per-file
percentages, same missing-line lists, 27 passed either way.

Getting there needed three separate fixes, and each failed as a flat **0% on
every file**, which is the same symptom that originally forced the vendoring.
Worth knowing because the symptom does not distinguish them:

1. **The child never starts coverage.** A spawned interpreter does not inherit
   the parent's `Coverage` object the way a fork does. Fixed with
   `COVERAGE_PROCESS_START` plus `_covstart/sitecustomize.py` calling
   `coverage.process_startup()`. Needs `parallel = true` (already set) so the
   children do not truncate each other's data, then a `coverage combine`.
2. **`pytest-cov` in the parent erases the children's data.** Run the parent
   with `--no-cov` and report from `coverage combine` afterwards.
3. **`source = ["src"]` measures nothing.** tox installs a wheel, so the child
   imports `coheriq` from `site-packages`, which `source = ["src"]` excludes --
   it yields 5 files at 0 lines each. `source_pkgs = ["coheriq"]` follows the
   import instead, with `[tool.coverage.paths]` mapping `site-packages` back
   onto `src/` so the report names source files.

`coverage-spawn.toml` holds (3); it is separate from `pyproject.toml` because
the spawn and fork paths genuinely need different `run` sections.

Reproduce:

    rm -f .coverage*
    COVERAGE_PROCESS_START=$PWD/tools/spawn-isolation/coverage-spawn.toml \
      PYTHONPATH=tools/spawn-isolation \
      python -m pytest -p pytest_isolate_spawn --isolate -q --no-cov test/
    python -m coverage combine -q --rcfile=tools/spawn-isolation/coverage-spawn.toml
    python -m coverage report --rcfile=tools/spawn-isolation/coverage-spawn.toml

Cost: 6.5s vs 0.46s forked. Starting coverage dominates the per-test constant,
so this is the case that most wants `pytest-xdist` underneath it.

## Not addressed
- **Windows actually run.** The code path uses no POSIX-only calls, which is
  not the same as having been tested on Windows.
- **MPI.** Irrelevant here, but noted for the sibling case: under
  `mpirun -n N pytest`, MPI owns the process topology and pytest runs inside
  it. A per-test spawn from inside a rank is not a rank -- `COMM_WORLD` is
  size 1 and collectives hang or silently test nothing. The two designs cannot
  both own process creation; a real plugin should hard-error on
  `--isolate` combined with `--only-mpi` rather than fail subtly.
