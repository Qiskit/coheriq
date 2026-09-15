##########
User guide
##########

This guide is for people who **use** a library that has been built with
Coheriq and want to turn on an acceleration engine for it.  You do not need to
understand how the framework works internally to follow it.

.. note::

   Activating an engine is done through Coheriq's own
   :func:`~coheriq.enable_engine` function, passing the *name of the library*
   (its domain name) and the engine you want.  You do not need the library to
   expose anything special for this — the same call works for every Coheriq
   library.  Consult your library's documentation for its domain name and the
   engine names available to it.


Install an engine
=================

An acceleration engine is typically a separate Python package from the library it
accelerates.  Install it the same way you install any other dependency, for
example:

.. code-block:: bash

   pip install mylib-fast-engine

Installing the engine does **not** change the library's behavior on its own.
Nothing is accelerated until you explicitly enable the engine (or set the
environment variable described below).


Query the available engines
===========================

Which engine names are available depends on what you have installed.  In the future, Coheriq is expected to provide a mechanism for querying them.  The name
you pass to :func:`~coheriq.enable_engine` is the engine
name that the engine package advertises.


Activate an engine
==================

There are two ways to activate an engine.  You must do so **before the first
use** of any accelerated functionality; otherwise, the default implementation is used.

In Python code
--------------

Call :func:`~coheriq.enable_engine` once, at program startup, before calling
anything else in the library.  Pass the library's domain name and the engine
name:

.. code-block:: python

   import coheriq
   import mylib

   coheriq.enable_engine("mylib", "fast-engine")

   # From here on, all accelerated functions dispatch to the engine.
   result = mylib.some_function(...)

Via an environment variable
---------------------------

If the library author has opted into it, you can select an engine without
touching the code, by setting an environment variable.  The exact variable name
is chosen by the library (it is derived from a prefix the author configures);
consult the library's documentation for the precise name.  For a library that
uses the prefix ``MYLIB``, the variable would be ``MYLIB_ENGINE``:

.. code-block:: bash

   MYLIB_ENGINE=fast-engine python my_script.py

This is convenient for switching engines between runs, or for enabling an
engine on an HPC cluster without editing the program.

Precedence
----------

If an engine is enabled explicitly in Python **and** an environment variable is
also set, the **explicit call wins**.  This lets a script pin a specific engine
regardless of the surrounding environment.


.. _before-first-use:

Activation rules
================

Engine activation follows a small, strict contract.  Keeping to it guarantees
predictable behavior:

- **Enable before first use.**  Activation must happen before any accelerated
  function or class is used.  Once the library has been used, the choice of
  implementation is locked in and can no longer be changed.
- **One engine at a time.**  A library can have at most one engine enabled.
- **Activation is one-way.**  You cannot switch to a different engine, nor
  disable an engine, later in the same process.  To use a different engine,
  start a new process.
- **Re-enabling the same engine is fine.**  Calling ``enable_engine`` again
  with the engine that is already active does nothing and is not an error.

If you enable an engine name that does not exist, Coheriq raises
:class:`~coheriq.CoheriqEngineNotFoundError`.

Reporting issues
================

Because the accelerated code and the library are typically maintained separately, it is encouraged to report
problems to the most appropriate place:

- If a problem occurs with **no engine enabled**, it is a library issue —
  report it to the library's issue tracker.
- If a problem occurs **only when a particular engine is enabled**, report it
  to that engine's issue tracker.
