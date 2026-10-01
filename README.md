# coheriq

**Swap in an accelerated implementation of a library — without changing the code that calls it.**

Coheriq is a dispatch decorator framework. A library marks certain functions and classes as *candidates for acceleration*; a separate, independently published package can then replace their implementations at runtime. The user enables the accelerated version by setting an environment variable or in one line of Python, and every call site transparently begins using it.

This lets acceleration be **optional** (users who can't or don't want the fast path keep the default, and pay none of its install cost), **decentralized** (a GPU/MPI/HPC engine ships as its own package, maintained by a different team), and **drop-in** (no call site changes).

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

## Stability policy

This library follows [semantic versioning 2.0.0](https://semver.org/). Semver allows a project in the `0.y.z` series to change anything at any time; Coheriq makes a stronger promise than that, so downstream **consumers** — the domains and engines that build against Coheriq's decorators — can depend on a version range rather than pinning an exact patchlevel or minor release.

Until the major version becomes non-zero:

- **Patchlevel** releases (`0.4.1` → `0.4.2`) contain bug fixes only. No new features.
- **Minor** releases (`0.4.2` → `0.5.0`) may add features, and do not break existing consumers. The end-user interface for enabling an engine may change in a minor release.
- A **breaking change** to the interface used by consumers advances the minor version to the next multiple of ten. If the current release is `0.4.2` and a breaking change lands on `main`, the next release is `0.10.0`.

Downstream packages should therefore depend on Coheriq as:

```
coheriq>=0.4,<0.10
```

That picks up bug fixes and new features automatically, and stops before the release that would require attention. Without the multiple-of-ten rule, a version number could not distinguish a release that adds features from one that breaks you, leaving `<0.5` as the only safe cap and a pin bump due on every feature release.

## Documentation

- [Conceptual overview](https://qiskit.github.io/coheriq/overview.html) — why Coheriq exists and how it fits together
- [User guide](https://qiskit.github.io/coheriq/guides/user-guide.html) — enabling an engine
- [Domain developer guide](https://qiskit.github.io/coheriq/guides/domain-development.html) — for library authors
- [Engine developer guide](https://qiskit.github.io/coheriq/guides/engine-development.html) — for engine authors
- [Design FAQ](https://qiskit.github.io/coheriq/design-faq.html)
- [Demonstrations](https://qiskit.github.io/coheriq/demos/index.html) — runnable notebooks, including [diamond inheritance](https://qiskit.github.io/coheriq/demos/diamond_inheritance.html) and [an engine with compiled code](https://qiskit.github.io/coheriq/demos/compiled_engine_example.html) (which can itself be found in the [`example/`](https://github.com/Qiskit/coheriq/tree/main/example) directory)
