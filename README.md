# coheriq

**Swap in an accelerated implementation of a library — without changing the code that calls it.**

Coheriq is a dispatch decorator framework. A library marks certain functions and classes as *candidates for acceleration*; a separate, independently published package can then replace their implementations at runtime. The user enables the accelerated version by setting an environment variable or in one line of Python, and every call site transparently begins using it.

This lets acceleration be **optional** (users who can't or don't want the fast path keep the default, and pay none of its install cost), **decentralized** (a GPU/MPI/HPC engine ships as its own package, maintained by a different team), and **drop-in** (no call site changes).

> [!NOTE]
> This repository is under active development and the code here should not be considered stable.

## The mental model: three parties

**1. The library (the "domain")** marks what *could* be accelerated and provides the default implementation:

```python
from coheriq import AccelerationDomain

_domain = AccelerationDomain("mylib", env_prefix="MYLIB")

@_domain.acceleration_candidate
def normalize(xs):
    total = sum(xs)
    return [x / total for x in xs]

_domain.materialize()
```

**2. An acceleration engine** — typically a separate package — provides a faster/better implementation of any subset of those candidates:

```python
from coheriq import AccelerationEngine

_engine = AccelerationEngine("mylib", "jax-accelerated")

@_engine.override
def normalize(xs):
    import jax.numpy as jnp
    a = jnp.asarray(xs)
    return (a / a.sum()).tolist()

_engine.materialize()
```

**3. The user** activates an engine once, before first use — and nothing else about their code changes:

```python
import coheriq
import mylib

coheriq.enable_engine("mylib", "jax-accelerated")

mylib.normalize([1.0, 2.0, 3.0])   # now runs on JAX, via the engine
```

Engines are ordinary Python classes under the hood, so independently developed engines can be combined through diamond inheritance into a hybrid that delivers all of their accelerations at once.

## Supported platforms

Coheriq targets Linux, macOS, and Windows. Its full test suite runs on Linux
and macOS, operating systems which support isolating each test in its own
process with `pytest --forked` (this relies on `os.fork()`). Windows is tested
in a more limited way, running the portions of the suite that do not require
`--forked`, until a fork-free way to run the rest is worked out.

## Documentation

- [Conceptual overview](docs/overview.rst) — why Coheriq exists and how it fits together
- [User guide](docs/guides/user-guide.rst) — enabling an engine
- [Domain developer guide](docs/guides/domain-development.rst) — for library authors
- [Engine developer guide](docs/guides/engine-development.rst) — for engine authors
- [Design FAQ](docs/design-faq.rst)
- [Demonstrations](docs/demos/) — runnable notebooks, including [diamond inheritance](docs/demos/diamond_inheritance.ipynb) and [an engine with compiled code](docs/demos/compiled_engine_example.ipynb) (which can itself be found in the [`example/`](example/) directory)
