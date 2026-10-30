# Spawn-based per-test isolation

Runs as `tox -e py-spawn` and `tox -e coverage-spawn`, alongside (not instead
of) the `--forked` defaults.  Windows CI runs both, so the registry-dependent
unit tests and their coverage are now exercised there.

Still exploratory in the sense that `--forked` remains the default everywhere
it works; these envs are the Windows path and a cross-check.

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

## Status

Added as extra envs, not as a replacement.  `--forked` stays the default on
POSIX: it is roughly an order of magnitude faster and is what the
`py`/`doctest`/`coverage` envs use.

    tox -e py-spawn         # unit tests, one fresh interpreter per test
    tox -e coverage-spawn   # same, with coverage (81%, matches forked)

## Measurements

26 tests (measured before #32 added one), Linux, Python 3.14:

| approach            | wall time |
| ------------------- | --------- |
| `--forked`          | 0.2s      |
| spawn, serial       | 4.5s      |
| spawn, 8 concurrent | 0.79s     |
| spawn, 16 concurrent| 0.53s     |

The per-test constant is a fraction of a second, most of it `import pytest`.
Embarrassingly parallel, so pairing this with `pytest-xdist` hides most of it.
The constant scales with import cost, so a Qiskit-sized import was **not**
measured and is the thing to check before trusting this elsewhere.

## The trap worth remembering

The first version of this plugin reported a segfaulting test as **nothing** --
a silent pass. A child killed by a signal writes no report, and absence read as
success.

The fix is in `pytest_runtest_protocol`: a missing `call` phase is treated as a
failure, not as silence. **Any** process-isolation scheme has this failure mode.

There is currently no automated check for this, which is the main gap in this
prototype. A real version needs a test that runs the plugin against a
deliberately crashing test and asserts the outcome is a failure -- which means
driving pytest from pytest, so it belongs in a harness like `pytester`, not in
a directory of files that nothing executes.

## Verified

Against `test/` on pytest 9.2.0 -- the version that breaks `pytest-forked`:

    pip install pytest-xdist          # optional, for -n
    PYTHONPATH=test/spawn_isolation \
      python -m pytest -p pytest_isolate_spawn --isolate -q test/

27 passed.

Crash reporting was checked separately, against throwaway tests that called
`os._exit(1)` and segfaulted via `ctypes.string_at(0)`: both report as
failures and the parent run survives. Those cases are not kept in the repo,
since nothing would run them -- see the note below on what a real version
would need.

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
    COVERAGE_PROCESS_START=$PWD/test/spawn_isolation/coverage-spawn.toml \
      PYTHONPATH=test/spawn_isolation \
      python -m pytest -p pytest_isolate_spawn --isolate -q --no-cov test/
    python -m coverage combine -q --rcfile=test/spawn_isolation/coverage-spawn.toml
    python -m coverage report --rcfile=test/spawn_isolation/coverage-spawn.toml

Cost: 6.5s vs 0.46s forked. Starting coverage dominates the per-test constant,
so this is the case that most wants `pytest-xdist` underneath it.

## Exposure to pytest/coverage internals

The relevant question is whether this inherits pytest-forked's periodic
breakage. It mostly does not, because the two cross the process boundary
differently.

pytest-forked ships a report object between processes: it copies
`rep.__dict__`, `marshal`s it, and rebuilds with `runner.TestReport(**d)`.
That couples it to the *internal layout* of a pytest class, which is not a
supported interface and is exactly what moved in 9.2. The vendored shim also
imports from `_pytest` in four places and reaches for `_pytest._code.getfslineno`.

This prototype sends plain JSON -- `when`, `outcome`, `longrepr` as a string,
`duration` -- and builds a fresh report in the parent. Those field *names* are
stable public API; no pytest object is serialized, so internal layout changes
cannot reach it.

Verified on an unpinned pytest 9.2.0: `marshal.dumps(report.__dict__)` raises
`ValueError` (the shim's failure) while the suite runs 27 passed through this
plugin.

What it touches:

| API | Status |
| --- | --- |
| `pytest.hookimpl`, `pytest.fail` | public |
| `pytest.TestReport`, `pytest.CallInfo.from_call` | public (re-exported) |
| `item.nodeid`, `item.location`, `item.config`, `item.ihook` | public |
| `config.rootpath` | public |
| `coverage.Coverage.current()`, `coverage.process_startup()` | public, documented |
| `item.session._setupstate.teardown_exact(nextitem)` | **private** |

One private call, and the shim needs the same one, so it is not a regression.
It is also the load-bearing line that makes fixtures tear down at the right
time -- there is no public equivalent. Risk if it moves: an `AttributeError`
at the first test, which is loud and immediate rather than silent.

Residual risks, in order:

1. `_setupstate` is renamed or `teardown_exact` changes signature. Loud.
2. `longrepr` is flattened to a string, so a failure shows pytest's rendered
   traceback rather than a live object. Cosmetic, already true today.
3. Coverage needs three cooperating pieces (see above), and a change in
   pytest-cov's data handling could reopen the 0% symptom. This is the part
   with the most moving parts and the least loud failure.

So: less exposed than pytest-forked, and the exposure that remains fails
noisily. The thing to actually watch is coverage, not pytest.

## Not addressed
- **Windows actually run.** The code path uses no POSIX-only calls, which is
  not the same as having been tested on Windows.
- **MPI.** Irrelevant here, but noted for the sibling case: under
  `mpirun -n N pytest`, MPI owns the process topology and pytest runs inside
  it. A per-test spawn from inside a rank is not a rank -- `COMM_WORLD` is
  size 1 and collectives hang or silently test nothing. The two designs cannot
  both own process creation; a real plugin should hard-error on
  `--isolate` combined with `--only-mpi` rather than fail subtly.
