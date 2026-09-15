#######
Coheriq
#######

**Swap in an accelerated implementation of a library — without changing the code that calls it.**

Coheriq is a dispatch decorator framework. A library marks certain
functions and classes as *candidates for acceleration*; a separate,
independently published package can then replace their implementations
at runtime. The user enables the accelerated version by setting an
environment variable or in one line of Python, and every call site
transparently begins using it.

This lets acceleration be *optional* (users who can't or don't want the fast
path keep the default, and pay none of its install cost), *decentralized* (a
GPU/MPI/HPC engine ships as its own package, maintained by a different team),
and *drop-in* (no call site changes).


The mental model: three parties
===============================

**1. The library (the "domain")** marks what *could* be accelerated and
provides the default implementation:

.. code-block:: python

   from coheriq import AccelerationDomain

   _domain = AccelerationDomain("mylib", env_prefix="MYLIB")

   @_domain.acceleration_candidate
   def normalize(xs):
       total = sum(xs)
       return [x / total for x in xs]

   _domain.materialize()

**2. An acceleration engine** — typically a separate package — provides a faster/better
implementation of any subset of those candidates:

.. code-block:: python

   from coheriq import AccelerationEngine

   _engine = AccelerationEngine("mylib", "jax-accelerated")

   @_engine.override
   def normalize(xs):
       import jax.numpy as jnp
       a = jnp.asarray(xs)
       return (a / a.sum()).tolist()

   _engine.materialize()

**3. The user** activates an engine once, before first use — and nothing else
about their code changes:

.. code-block:: python

   import coheriq
   import mylib

   coheriq.enable_engine("mylib", "jax-accelerated")

   mylib.normalize([1.0, 2.0, 3.0])   # now runs on JAX, via the engine

Engines are ordinary Python classes under the hood, so independently
developed engines can be combined through diamond inheritance into a
hybrid that delivers all of their accelerations at once.


License
-------

`Apache License 2.0 <https://github.com/Qiskit/coheriq/blob/main/LICENSE.txt>`_


.. toctree::
  :hidden:

   Documentation Home <self>
   Conceptual overview <overview>
   User guide <guides/user-guide>
   Domain developer guide <guides/domain-development>
   Engine developer guide <guides/engine-development>
   Design FAQ <design-faq>
   Demonstrations <demos/index>
   API References <apidocs/index>
