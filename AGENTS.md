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

# Lint (ruff format check, ruff check, mypy, pylint, copyright check)
tox -e lint

# Auto-fix style issues
tox -e style

# Build docs
tox -e docs
```

The `py`, `coverage`, and `doctest` tox environments run pytest with `--forked`, so each test runs in a subprocess. This is necessary because `AccelerationDomain` and `AccelerationEngine` use a global registry that cannot otherwise be reset between tests. `--forked` is set per-environment (in `tox.ini`), not in `pyproject.toml`, so if you invoke pytest directly on `test/` rather than through tox you must pass `--forked` yourself.

`--forked` relies on `os.fork()` and so does not run on Windows. The envs that need it are therefore Linux/macOS only; the in-process suites below (`notebook`, `ragged`, `ragged-engine`) are what CI runs on Windows.

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

1. **Domain** (addon/library code) — Creates an `AccelerationDomain`, decorates functions with `@domain.acceleration_candidate`, then calls `domain.materialize()`. This locks in the default implementations and makes the wrapped callables available to users.

2. **Engine** (accelerator code) — Creates an `AccelerationEngine(domain_name, engine_name)`, decorates override functions with `@engine.override`, then calls `engine.materialize()`. The engine uses Python class inheritance (`type(...)`) internally, so engines can inherit from other engines (including diamond inheritance, which is exercised in `docs/demos/diamond_inheritance.ipynb`).

3. **User code** — Calls `coheriq.enable_engine(domain_name, engine_name)` once at startup to activate an engine. After that, all wrapped callables silently dispatch to the engine's overrides. Activation is a free function rather than a method on the domain; `docs/design-faq.rst` records why.

### Module layout

`src/coheriq/__init__.py` only re-exports the public API; the implementation is split across:

- `domain.py` — `AccelerationDomain`, the global domain registry, and the `acceleration_candidate` decorator.
- `engine.py` — `AccelerationEngine` and the `override` decorator.
- `activation.py` — `enable_engine`, plus engine discovery via entry points.
- `exceptions.py` — the `CoheriqError` hierarchy.

Imports run one way: `activation` imports both `domain` and `engine`, and `engine` imports `domain`. The single exception is the environment-variable activation path in `domain._ensure_realized_impl`, which imports `activation` function-locally to keep the module-level graph a DAG.

### Key implementation details

- **Global registry**: `_domain_registry` maps domain names to `AccelerationDomain` instances. It is protected by `_domain_registry_lock`. This global state is why tests use `--forked`.
- **Lazy dispatch**: Each wrapped function caches its resolved implementation in a `nonlocal f_impl` closure variable. The first call resolves the implementation; subsequent calls go directly to it with no extra overhead.
- **State machines**: `AccelerationDomain` and `AccelerationEngine` each enforce strict state transitions to prevent misuse, and they are *different* machines. A domain goes `CONSTRUCTING → MATERIALIZED`, then branches to either `CALLED_WITHOUT_ENGINE` or `ENGINE_ENABLED`. An engine goes `CONSTRUCTING → MATERIALIZED → ENABLED`. Neither machine has a reverse transition: activation is one-way by design, which is why tests isolate with `--forked` rather than resetting state.
- **Lock ordering**: To avoid deadlock, the domain lock is always acquired before an engine lock. This convention is documented in a comment in `enable_engine` (`activation.py`).
- **Type-checking bypass**: The `acceleration_candidate` decorator returns the original class (not the wrapper) under `TYPE_CHECKING`, so type checkers see the real type rather than a `Callable`.

### `name` parameter

Both `acceleration_candidate` and `override` accept a `name` parameter to specify an explicit lookup name instead of using `f.__name__`. This is important when the override function has a different name from the candidate, or when fully-qualified names are needed to avoid collisions across modules.
