######################
Engine developer guide
######################

This guide is for **engine authors** — typically HPC developers writing an
accelerated re-implementation of some part of a library.  Coheriq allows for an engine to be a
separate, independently published package.  You do not need to modify the
library you accelerate; you only need to know the domain name it registered and
the names of the candidates you want to override.

If you have not already, read the :doc:`conceptual overview <../overview>`.


Set up an engine
================

An **engine** targets an existing domain by name, registers overrides for some
subset of that domain's candidates, and then materializes.  You only need to
override the candidates you actually accelerate — accelerating even a single
function is enough to justify publishing an engine.

A typical engine package's ``myengine/_overrides.py``:

.. code-block:: python

   from coheriq import AccelerationEngine

   # The first argument is the *domain* name the library registered.
   _engine = AccelerationEngine("mylib", "fast-engine")
   _override = _engine.override

   # Import every module that has an `@_override` decorator.
   from . import solver_fast  # noqa: E402

   _engine.materialize()

And in ``myengine/solver_fast.py``:

.. code-block:: python

   from . import _override

   @_override(name="solve")
   def solve_fast(problem):
       ...

The ``name`` you pass to ``override`` must match the name the candidate was
registered under in the domain (its ``__name__`` by default, or the explicit
``name`` the library author chose).  You may name your override function
whatever you like; the ``name`` is what links it to the candidate.  Overriding a
name that the domain did not register raises
:class:`~coheriq.CoheriqEngineError`.

As with domains, every module containing an ``@_override`` must be imported
before ``materialize()`` is called.


Combining engines through inheritance
=====================================

An engine is, under the hood, an ordinary Python class that inherits from the
domain's class.  This means engines compose through normal multiple inheritance
and method resolution order (MRO).

Suppose two engines already exist for the same domain — one accelerates
``solve`` and another accelerates ``recover`` — and were developed
independently.  You can publish a third engine that inherits from both and so
delivers *both* accelerations, with almost no code of its own:

.. code-block:: python

   from coheriq import AccelerationEngine

   # Base engines are given in MRO order.  They may be passed as engine
   # instances or by name (if already registered in the domain).
   _hybrid = AccelerationEngine("mylib", "hybrid", ["fast-solver", "fast-recover"])
   _hybrid.materialize()

Each base engine must itself be materialized before the engine that inherits
from it can be materialized.  This composition supports the **diamond
inheritance** pattern, worked through in the
:doc:`diamond inheritance demonstration <../demos/diamond_inheritance>`.

Any hybrid engine you assemble this way should be tested before use, just like
any other engine — the composition is only as correct as the pieces and their
interaction.


Make your engine discoverable with entry points
===============================================

You want a user to be able to write ``coheriq.enable_engine("mylib", "fast-engine")``
*without* first importing your package by name.  Requiring the import would
couple their code to your engine's import path — exactly the coupling Coheriq
exists to remove.

Python **entry points** solve this.  Declare your engine in your package's
``pyproject.toml`` under the group ``coheriq.engines.<domain_name>``:

.. code-block:: toml

   [project.entry-points."coheriq.engines.mylib"]
   fast-engine = "myengine._overrides"

The target is the **module** whose import constructs and materializes your
engine (here, the ``myengine`` package's ``_overrides``).  When a user calls
``coheriq.enable_engine("mylib", "fast-engine")``, Coheriq looks up this entry
point, imports the module on demand — which registers your engine as a side
effect — and enables it.

The group is namespaced by domain name so that two different domains can never
collide on an engine name, and enabling one engine never imports another's
module.

.. note::

   Discovery is **lazy**: :func:`~coheriq.enable_engine` imports only the one
   engine being requested.  This matters because engines may pull in heavy
   dependencies (CUDA, MPI, …), and a user should not pay to import an engine
   they are not enabling.


Pin to the library's minor version
==================================

Your engine reaches into a specific version of the library's internals and
mirrors its interface, so compatibility is version-sensitive.

- **Pin the library to a compatible minor version** in every branch and release
  of your engine.  Using an engine against a library version whose
  compatibility is unknown risks a poor user experience.
- **Subscribe to the library's releases.**  After a new minor release, update
  your engine to be compatible; once its test suite passes against the new
  version, cut a new release of your engine.


Test against the library's suite
================================

The library's test suite effectively defines the interface your engine must
satisfy.  Running it against your engine is the best way to demonstrate — to
yourself and to users — that your engine is a correct drop-in replacement.

- **Run the library's test suite against your engine, in CI.**  Ideally your CI
  clones the library's latest ``stable/*`` branch and runs its suite with your
  engine enabled.
- **Test against the library's development version too**, so you learn about
  breaking changes early.  A tool such as
  `extremal-python-dependencies <https://pypi.org/project/extremal-python-dependencies/>`_
  can help you exercise the newest (or oldest) permissible dependency versions.
- **Mark tests as** ``xfail`` **only when justified.**  If you believe a test
  should not be expected to pass against your engine, marking it ``xfail`` on
  your branch is acceptable — but it should prompt a conversation with the
  library authors about whether the test or your implementation should change.
- **Watch for tests worth upstreaming.**  If you find gaps or improvements in
  the library's suite, propose them upstream.  A stronger shared suite benefits
  every engine.  Likewise, if correctness is solid but a floating-point
  tolerance is too tight for your implementation, propose a looser tolerance to
  the library rather than carrying a local patch.


Handle threading and errors for your execution model
====================================================

Responsibility for the execution model rests with you, the engine author, not
the user:

- **Own the threading.**  Manage any internal parallelism (OpenMP, Rayon, Julia
  threads, …) and avoid resource contention.  You may generally assume the
  library's API is called from a single thread, per the library's documented
  contract.
- **Follow fail-stop semantics under collective multi-process execution.**  A
  function called collectively must not raise or abort on only a single process; on
  error, abort the execution context collectively (e.g. ``MPI_Abort``).  Making
  the error visible on all processes is best-effort only and must not be relied
  on for recovery.
