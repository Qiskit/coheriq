######################
Domain developer guide
######################

This guide is for **library authors** — the developers of the addon or library
whose functionality might one day be accelerated.  Your job is to create an
:class:`~coheriq.AccelerationDomain`, mark the functions and classes that are
candidates for acceleration, and design your API so that acceleration is
actually possible later.

If you have not already, read the :doc:`conceptual overview <../overview>` for
the three-party model and vocabulary.


Set up a domain
===============

A **domain** is your library's registry of acceleration candidates.  Create one
at your package's top level, expose its decorator, import every module that
uses the decorator, and then call ``materialize()``.

A typical ``mylib/__init__.py``:

.. code-block:: python

   from coheriq import AccelerationDomain

   _domain = AccelerationDomain("mylib")
   _acceleration_candidate = _domain.acceleration_candidate

   # Import every module that has an `@_acceleration_candidate` decorator so
   # that the candidates are registered before we materialize.
   from . import linalg  # noqa: E402
   from . import solver  # noqa: E402

   _domain.materialize()

And in, say, ``mylib/solver.py``:

.. code-block:: python

   from . import _acceleration_candidate

   @_acceleration_candidate
   def solve(problem):
       ...

The domain name (``"mylib"`` above) must be unique across the process and is
the name engine authors will reference.

.. important::

   Every function or class decorated with ``@_acceleration_candidate`` must be
   imported **before** ``materialize()`` is called.  Marking a candidate after
   the domain is materialized raises :class:`~coheriq.CoheriqDomainError`.  This
   is why the top-level module imports its submodules before materializing.

   Be careful that these imports do not eagerly pull in heavyweight
   dependencies (see :ref:`no-heavy-imports`).


Naming candidates
=================

By default a candidate is registered under the decorated object's ``__name__``.
When two candidates in different modules share a name, pass an explicit
``name`` that is unique:

.. code-block:: python

   @_acceleration_candidate(name="solver__solve")
   def solve(problem):
       ...

The ``name`` you choose here is the lookup key an engine author must use in
their ``override``.  Choosing stable, unambiguous names is part of your API
contract.


Marking classes
===============

The decorator works on classes as well as functions.  This is useful for data
container classes that an engine may wish to replace with a layout that is more
amenable to acceleration (better memory alignment, cache locality, etc.):

.. code-block:: python

   @_acceleration_candidate
   class Bitstrings:
       ...

See :ref:`class-limitations` for the constraints this places on how such a
class may be used.


Activation needs nothing from you
=================================

You do **not** need to expose an activation function of your own.  Users
activate an engine with Coheriq's :func:`~coheriq.enable_engine`, passing your
domain name:

.. code-block:: python

   import coheriq

   coheriq.enable_engine("mylib", "fast-engine")

The domain name is the only identifier a user needs, and the call is the same
for every Coheriq library — so you have nothing to re-export and nothing extra
to document.  You can simply point your users at Coheriq's own
:doc:`user guide <user-guide>`.

Opting into environment-variable activation
-------------------------------------------

If you want users to be able to select an engine without editing code, pass an
``env_prefix`` when constructing the domain:

.. code-block:: python

   _domain = AccelerationDomain("mylib", env_prefix="MYLIB")

With this set, Coheriq will consult the ``MYLIB_ENGINE`` environment variable on
first use and enable the named engine automatically.  An explicit
:func:`~coheriq.enable_engine` call still takes precedence over the variable.


Write a good API for acceleration
=================================

Parallelism cannot be bolted on after the fact.  The single most important
thing you can do is design your public API so that an accelerated
implementation is *possible*.

Separate computation from execution
-----------------------------------

Keep **execution parameters** out of your computational functions.  A function
signature should describe *what* to compute, not *how* to run it.

- **Computational arguments** describe the calculation itself (a matrix, a
  threshold, a Hamiltonian).  These belong in your API.
- **Execution arguments** only affect how the computation runs (number of
  processes, thread counts, tiling/block sizes, choice of BLAS,
  ``mpirun`` options).  These do **not** belong in your computational API.

When execution details are baked into a function signature, the API becomes
coupled to one execution model and an engine that runs on GPUs, or across MPI
ranks, cannot present the same interface.  Configure execution globally (or via
an opaque ``execution_context`` argument) instead of per call.

Document the threading and multi-process contract
-------------------------------------------------

State clearly, in your own documentation, how your API may be called:

- As a starting point, you may decide to specify that your API is meant to be called from a
  **single thread** (the main thread) unless stated otherwise.  This frees
  engine authors from having to make accelerated code re-entrant.
- If any function supports collective multi-process execution, document whether
  it is called from all processes or only the control process, how arguments
  must agree across processes, and the return-value and error semantics.

Prefer opaque intermediate types where it helps
-----------------------------------------------

For values that are produced by one of your functions and consumed by another,
consider an opaque type rather than a concrete one (e.g. a plain NumPy array).
An opaque return type gives an engine author freedom to use a representation
with better performance characteristics without changing your API.


.. _no-heavy-imports:

Don't eagerly load heavyweight dependencies
===========================================

Your package should not import and initialize heavyweight dependencies at
import time.  Import them lazily, inside the functions that need them.  This
keeps time-to-import low and honors the principle that a user should only pay
for what they use — someone who never triggers the accelerated path should not
pay for its dependencies.

This applies to the import-before-``materialize()`` step above: importing your
submodules to register their candidates should not, as a side effect, drag in a
heavy dependency.


Write robust tests
==================

Your test suite effectively *defines* the interface an engine must satisfy, so
it is one of the most valuable things you provide to engine authors.  Expect
engine developers to run your test suite against their engine.

- Aim for a test suite that can be run against an engine with a single switch
  (e.g. one extra pytest argument, or an environment variable), so verifying an engine is a one-line
  operation.
- Historically, floating-point tests compare against expected values within a
  tolerance (``pytest.approx``) rather than requiring bit-for-bit
  reproducibility, because results differ across architectures and BLAS
  implementations.  An engine author may occasionally need a looser tolerance;
  when they have strong confidence in correctness, encourage them to propose
  the adjusted tolerance back to your repository.
- Be receptive to test improvements proposed by engine authors — they exercise
  your interface from an angle you may not have.


.. _class-limitations:

Limitations
===========

When you mark a **class** as an acceleration candidate, it is replaced at
activation time by a dynamically created class.  As a result, some ordinary
class features do not behave as expected:

- ``isinstance`` and ``issubclass`` checks against the marked class are not
  reliable under replacement.
- Subclassing the marked class is not supported.
- ``@classmethod`` does not work on a marked class.  ``@staticmethod`` does
  work.
- Class attributes are not reliably available prior to instantiation.

These constraints are acceptable for the intended use case: marking classes
that serve as **data containers**, where construction-time dispatch and
composition are preferable to inheritance-based polymorphism.  Do not mark
classes that are meant to be used as behavioral base classes.
