# AGENTS.md

## Commands

Tests are managed via tox.

```bash
# Run unit tests
tox -e py

# Run unit tests for a specific Python version
tox -e py314

# Run a single test file or test
tox -e py -- test/test_engine.py::TestEngineEnablement::test_override

# Run doctests
tox -e doctest

# Run notebook tests against the pure-Python default backend
tox -e notebook

# Run the same notebook tests against the compiled C++ "fused" engine
tox -e notebook-engine

# Run the example domain's test suite against the default and the C++ engine
tox -e ragged
tox -e ragged-engine

# Run coverage (includes doctests)
tox -e coverage

# Run the unit tests with spawn-based isolation instead of --forked.
# This is how the suite runs on Windows, which has no os.fork().
tox -e py-spawn
tox -e coverage-spawn

# Lint (ruff format check, ruff check, mypy, pylint, copyright check)
tox -e lint

# Auto-fix style issues
tox -e style

# Build docs
tox -e docs
```

The `py`, `coverage`, and `doctest` tox environments run pytest with `--forked`, so each test runs in a subprocess. This is necessary because `AccelerationDomain` and `AccelerationEngine` use a global registry that cannot otherwise be reset between tests. `--forked` is set per-environment (in `tox.ini`), not in `pyproject.toml`, so if you invoke pytest directly on `test/` rather than through tox you must pass `--forked` yourself.

`--forked` relies on `os.fork()` and so does not run on Windows. The `py-spawn` and `coverage-spawn` envs cover that gap by spawning a fresh interpreter per test instead of forking. The plugin behind them lives at `test/spawn_isolation/`, alongside the vendored `pytest-forked` in `test/coverage_startup/`. Both directories are named in `addopts` as `--ignore`, following the existing convention; neither holds a file matching `test_*.py`, so nothing in them is collected either way.

Neither spawn env is in `envlist`, so a bare `tox` does not run them. `--forked` remains the default on POSIX because it is roughly an order of magnitude faster. The Windows CI job's `toxenv` lists which envs run there.

`doctest` still needs `--forked` and so remains Linux/macOS only.

### The example engine (`example/engine`) is a compiled C++/nanobind package

`coheriq_ragged_engine` is built with **scikit-build-core + CMake + nanobind**, so the `notebook`, `notebook-engine`, and `ragged-engine` tox environments require a **C++ toolchain** (a compiler plus CMake; nanobind is pulled into the isolated build environment automatically). `tox -e ragged` installs only the pure-Python domain and needs no compiler.

For local iteration on the C++ source, an editable install that rebuilds on change:

```bash
pip install --no-build-isolation -e ./example/engine -C editable.rebuild=true
```

The example domain (`example/domain`) test suite runs **in-process** (the `ragged`/`ragged-engine` envs do not pass `--forked`): it uses a single domain activated one way per process, selected by the `RAGGED_ENGINE` environment variable.

## Architecture

Coheriq is a **dispatch decorator framework** that allows a library (the "domain") to mark certain functions as candidates for acceleration, and then lets an engine provider swap in alternative implementations at runtime without changing the calling code.

### Three-party model

1. **Domain** (addon/library code) — Creates an `AccelerationDomain`, decorates functions with `@domain.acceleration_candidate`, then calls `domain.materialize()`. This builds the class that is the domain's **reference implementation** and makes the wrapped callables available to users.

2. **Engine** (accelerator code) — Creates an `AccelerationEngine(domain_name, engine_name)`, decorates override functions with `@engine.override`, then calls `engine.materialize()`. The engine uses Python class inheritance (`type(...)`) internally, so engines can inherit from other engines (including diamond inheritance, which is exercised in `docs/demos/diamond_inheritance.ipynb`).

3. **User code** — Calls `coheriq.enable_engine(mylib, engine_name)` once at startup to activate an engine, passing the library module (its domain name is also accepted). After that, all wrapped callables silently dispatch to the engine's overrides. Activation is a free function rather than a method on the domain; `docs/design-faq.rst` records why.

The reference implementation is an engine, not a separate kind of thing: every engine's class inherits from the domain's, and dispatch does not branch on the two cases. It is named `coheriq.REFERENCE` (the string `"reference"`), a name `AccelerationEngine` refuses because the domain owns it. `enable_engine(domain, coheriq.REFERENCE)` pins it, which differs from simply not choosing, because an explicit call takes precedence over the domain's environment variable. `coheriq.available_engines(domain)` lists the enableable names, always leading with `"reference"`, so the result is never empty; `coheriq.active_engine(domain)` returns the active name, or `None` while nothing has been resolved yet.

### Module layout

`src/coheriq/__init__.py` only re-exports the public API; the implementation is split across:

- `domain.py` — `AccelerationDomain`, the global domain registry, and the `acceleration_candidate` decorator.
- `engine.py` — `AccelerationEngine` and the `override` decorator.
- `activation.py` — `enable_engine`, plus engine discovery via entry points.
- `exceptions.py` — the `CoheriqError` hierarchy, plus the `CoheriqWarning` hierarchy.

Imports run one way: `activation` imports both `domain` and `engine`, and `engine` imports `domain`. The single exception is the environment-variable activation path in `domain._ensure_realized_impl`, which imports `activation` function-locally to keep the module-level graph a DAG.

### Key implementation details

- **Global registry**: `_domain_registry` maps domain names to `AccelerationDomain` instances. It is protected by `_domain_registry_lock`. This global state is why tests use `--forked`.
- **Lazy dispatch**: Each wrapped function caches its resolved implementation in a `nonlocal f_impl` closure variable. The first call resolves the implementation; subsequent calls go directly to it with no extra overhead.
- **State machines**: `AccelerationDomain` and `AccelerationEngine` each enforce strict state transitions to prevent misuse, and they are *different* machines. A domain goes `CONSTRUCTING → MATERIALIZED`, then branches to either `CALLED_WITHOUT_ENGINE` or `ENGINE_ENABLED`. An engine goes `CONSTRUCTING → MATERIALIZED → ENABLED`. Neither machine has a reverse transition: activation is one-way by design, which is why tests isolate with `--forked` rather than resetting state.
- **Lock ordering**: To avoid deadlock, the domain lock is always acquired before an engine lock. This convention is documented in a comment in `enable_engine` (`activation.py`).
- **Type-checking bypass**: The `acceleration_candidate` decorator returns the original class (not the wrapper) under `TYPE_CHECKING`, so type checkers see the real type rather than a `Callable`.

### Domain names are module names

A domain's name should be the `__name__` of the module it belongs to — the name the library is imported under, which is not always the name it is distributed under, so a project published as `my-lib` and imported as `my_lib` should have a domain name of `my_lib`. Constructing the domain in a submodule is fine, as the name need only be *an importable module*. This is what lets a module stand in for a domain anywhere a domain is accepted, which removes the import-order hazard in the string form: a domain is registered as a side effect of importing its library, so a name can only be resolved after that import, whereas a module cannot be named before it.

`AccelerationDomain` warns (`CoheriqDomainWarning`) when its name does not resolve to an importable module. The convention is advisory, because a domain defined in a script, a notebook, or a test has no module to be named after — `docs/demos/diamond_inheritance.ipynb` is a deliberate example, and the test suite filters the warning in `pyproject.toml`. The check runs at construction, so the warning points at the line that passes the name, and it never imports the name it checks.

<<<<<<< HEAD
Module resolution is by name only. No record is kept of which module defined a domain, which keeps the convention the single source of truth, and a submodule therefore does not resolve to its parent.

`_resolve_domain` lives in `domain.py`, because `activation.py` and `engine.py` both need it and `engine.py` cannot import from `activation.py` without creating a cycle. It takes the exception to raise for an unregistered name, because the callers classify that mistake differently: it is a `CoheriqUserError` from `enable_engine` but a `CoheriqLibraryError` from `AccelerationEngine`. An argument that cannot name a domain at all is a `TypeError` either way, so the resolver raises that itself.
=======
Module resolution is by name only (`_domain_name_from_module` in `domain.py`, used by both `activation._resolve_domain` and `AccelerationEngine.__init__`). No record is kept of which module defined a domain, which keeps the convention the single source of truth. A submodule therefore does not resolve to its parent; the error message suggests the parent instead.

`_resolve_domain` lives in `activation.py`, but `engine.py` cannot import it without creating a cycle, so the module-to-name step lives in `domain.py` — the one module both already import.
>>>>>>> origin/main

### `name` parameter

Both `acceleration_candidate` and `override` accept a `name` parameter to specify an explicit lookup name instead of using `f.__name__`. This is important when the override function has a different name from the candidate, or when fully-qualified names are needed to avoid collisions across modules.
