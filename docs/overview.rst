###################
Conceptual overview
###################

Coheriq is a **dispatch decorator framework**.  It lets a library mark certain
functions and classes as candidates for acceleration, and then lets a separate
package swap in alternative implementations at runtime — without changing any
of the code that calls those functions.

This page explains *why* the framework is shaped the way it is and introduces
the vocabulary used throughout the rest of the documentation.  If you would
rather see working code first, start with the :doc:`demonstrations
<../demos/index>`.


Motivation
==========

High-performance re-implementations of a library's functionality often come
with heavyweight or non-portable requirements: a particular GPU, an MPI
installation built against a specific system, or a compiler toolchain that not
every user has.  Folding such an implementation directly into the library would
force that cost on everyone and make the accelerated behavior a mandatory,
un-opt-out-able upgrade.

Coheriq exists so that acceleration can be **optional, decentralized, and
drop-in**:

- **Optional** — a user who cannot (or does not want to) run the accelerated
  code keeps the library's default behavior, and pays none of the accelerated
  implementation's installation or import cost.
- **Decentralized** — an acceleration engine can be developed, versioned, and
  published independently of the library it accelerates, by a different team or
  even a different organization.  The library author does not have to review or
  merge a large, specialized pull request to make acceleration available.
- **Drop-in** — enabling an engine requires **no change to any call site**.
  The user activates an engine in one line at startup (or by setting an environment variable), and every marked
  function transparently begins dispatching to the accelerated implementation.

That last property is the defining feature.  Coheriq does not hand your code an
object to call; it rewires the existing functions in place.

What an engine substitutes
==========================

It helps to be precise about *what* gets replaced.  An engine does not merely
supply faster code for a function; it substitutes a **coherent unit of
behavior, state, and invariants** — a data representation, a device context, an
execution model — chosen as a whole.  Enabling an engine is closer to selecting
a *policy* for how a body of work is carried out than to patching an individual
mechanism.  Everything the engine touches then behaves according to that single,
self-consistent choice.

That word *coherent* is deliberate, and it is where the name **Coheriq** comes
from.  The framework is built so that an implementation is swapped as one
coherent piece rather than assembled from independently overridden fragments —
which is what keeps the result consistent, composable, and easy to reason about.
The :doc:`design FAQ <../design-faq>` develops why substituting whole units is
preferable to overriding individual functions.


The three parties
=================

Coheriq is built around a three-party model.  Each party has a distinct role
and a distinct guide in this documentation.

Domain (the library)
    The library that owns the functionality.  It creates an
    :class:`~coheriq.AccelerationDomain`, marks functions and classes with the
    ``@domain.acceleration_candidate`` decorator, and calls
    ``domain.materialize()`` to lock in the defaults.  See the
    :doc:`domain developer guide <../guides/domain-development>`.

Engine (the accelerator)
    A separate module -- often a separate *package* -- that provides accelerated
    implementations.  It creates an :class:`~coheriq.AccelerationEngine` for a
    named domain, marks its replacements with ``@engine.override``, calls
    ``engine.materialize()``, and advertises its existence via Python entry points.  See the
    :doc:`engine developer guide <../guides/engine-development>`.

User (the caller)
    Application code that uses the library.  The user activates an engine once
    and otherwise writes code exactly as they would against the
    unaccelerated library.  See the :doc:`user guide <../guides/user-guide>`.


The activation contract
=======================

The rules governing engine activation are deliberately restrictive.  Each
restriction removes a class of failure mode rather than limiting anything a
user realistically needs to do.

One engine per domain
    A domain can have at most one engine enabled at a time.

Process-global
    Activation applies to the whole process.  It is unlikely that different
    parts of the same program need different implementations of the same
    library, and a global choice keeps the model simple.

One-way
    Once an engine is enabled it cannot be swapped for another or disabled.
    There is no reset in the public API.

Before first use
    An engine must be enabled *before* any marked function or class is used.
    After first use, the default (or already-active) implementation is locked
    in; switching then could leave data structures in an inconsistent state,
    mixing the library-native and accelerated representations.

Re-enabling is harmless
    Enabling the engine that is already active is treated as an idempotent
    no-op rather than an error, which is convenient when startup code might run
    more than once.

An engine can be activated in two ways: explicitly, by calling
:func:`coheriq.enable_engine` in Python, or implicitly, through an environment
variable that the domain author opts into.  When both are present, the
**explicit call takes precedence**.  See the
:doc:`user guide <../guides/user-guide>` for details.


Composition through inheritance
===============================

Under the hood, ``materialize()`` uses :func:`type` to build a class for the
domain's defaults, and each engine builds a class that inherits from that
domain class.  Because engines are ordinary Python classes, one engine can be
built from others: an engine may declare **base engines**, and Python's normal
method-resolution order composes their overrides.

This makes it possible to combine independently developed engines.  If one
engine accelerates function ``A`` and another accelerates function ``B``, a
third engine can inherit from both and provide accelerated versions of *both*
``A`` and ``B`` with very little supporting code — including the diamond
inheritance pattern.  The :doc:`diamond inheritance demonstration
<../demos/diamond_inheritance>` walks through a concrete example.


Limitations
===========

Because a marked class is replaced by a constructor function that dynamically creates the activated class, a few Python features do not behave as they would for an
ordinary class.  These are covered in detail in the
:doc:`domain developer guide <../guides/domain-development>`; in brief:

- ``isinstance`` and ``issubclass`` checks against a marked class are not
  reliable under replacement.
- Subclassing a marked class is not supported.
- ``@classmethod`` does not work on a marked class (``@staticmethod`` does).
- Class attributes are not reliably available before instantiation.

These trade-offs are acceptable for the intended use case: marking classes that
act as **data containers** rather than behavioral base classes.
