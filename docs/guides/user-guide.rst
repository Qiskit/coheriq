##########
User guide
##########

This guide is for people who **use** a library that has been built with
Coheriq and want to turn on an acceleration engine for it.  You do not need to
understand how the framework works internally to follow it.

Everything here is done through Coheriq's own functions.  The library you are
accelerating does not have to expose anything special, so the same four steps
work for every Coheriq library:

#. :ref:`Import the library <ug-import>` and confirm it declares a domain.
#. :ref:`List the engines <ug-list>` available for it.
#. :ref:`Install an engine <ug-install>`, if the one you want is not there yet.
#. :ref:`Activate it <ug-activate>` at startup.

Throughout, the library being accelerated is called ``mylib``.  Substitute the
library you are actually using.


.. _ug-import:

Confirm the library declares a domain
=====================================

A library that offers acceleration registers a **domain** — its list of
functions and classes that an engine may replace.  Registration happens as a
side effect of importing the library, so the first step is simply to import it:

.. code-block:: python

   >>> import coheriq
   >>> import mylib

:func:`~coheriq.known_domains` then reports the domains registered so far,
which confirms whether the import gave you one:

.. code-block:: python

   >>> coheriq.known_domains()
   ('mylib',)

A domain is conventionally named after the module it belongs to, which is why
``mylib`` appears here under the name you imported.  If the library you expected
is missing from this list, it does not declare a domain, and nothing in this
guide applies to it.  Check its documentation for whether it supports Coheriq,
and whether the version you have does.

This call reports only what the current process has imported.  A library that is
installed but not yet imported has registered nothing, so import first and ask
afterwards.


.. _ug-list:

List the available engines
==========================

:func:`~coheriq.available_engines` lists the engine names you can enable for a
domain.  Pass it the library itself:

.. code-block:: python

   >>> coheriq.available_engines(mylib)
   ('reference',)

Every library has at least one entry: ``'reference'``, its own implementation.
In the current version of Coheriq it comes first and is the one you get if you
enable nothing.  Any other names are acceleration engines you have installed.

The single entry above is therefore the answer on a machine with no engine
installed, and the next section is where to start.  If you already see a name
beyond ``'reference'``, that engine is ready and you can skip ahead to
:ref:`activation <ug-activate>`.

Asking this question does not activate anything, and it does not import the
engine packages it names.  An engine can advertise itself without having been
imported yet, so a listed name means :func:`~coheriq.enable_engine` will try it,
not that it is guaranteed to load.

:func:`~coheriq.active_engine` answers the companion question — which engine, if
any, has been settled on.  It returns ``None`` until one is resolved:

.. code-block:: python

   >>> coheriq.active_engine(mylib) is None
   True

Neither call resolves or freezes the implementation, so both are safe to run
before deciding what to enable.


.. _ug-install:

Install an engine
=================

An acceleration engine is often a separate Python package from the library
it accelerates, and which engines exist is up to the library and its ecosystem.
Consult your library's documentation for the ones it recommends.  Install an
engine the same way you install any other dependency, for example:

.. code-block:: bash

   pip install mylib-fast-engine

Installing the engine does **not** change the library's behavior on its own.
Nothing is accelerated until you activate it.  After installing, the new engine
appears alongside ``'reference'`` in a fresh process:

.. code-block:: python

   >>> coheriq.available_engines(mylib)
   ('reference', 'fast-engine')

Note that the name you enable is ``'fast-engine'``, not the
``mylib-fast-engine`` you installed.  A package chooses its engine name
independently of its distribution name, so take the name to enable from
:func:`~coheriq.available_engines` or the engine's documentation rather than
from the ``pip install`` line.


.. _ug-activate:

Activate an engine
==================

There are two ways to activate an engine.  You must do so **before the first
use** of any accelerated functionality; otherwise, the library's reference
implementation is used.

In Python code
--------------

Call :func:`~coheriq.enable_engine` once, at program startup, before calling
anything else in the library.  Pass the library itself and the engine name:

.. code-block:: python

   import coheriq
   import mylib

   coheriq.enable_engine(mylib, "fast-engine")

   # From here on, all accelerated functions dispatch to the engine.
   result = mylib.some_function(...)

.. _passing-the-module:

Why pass the module?
~~~~~~~~~~~~~~~~~~~~

A library's domain is registered as a side effect of importing it, so Coheriq
can only look up a library it has already seen.  Passing the module makes that
ordering impossible to get wrong: you cannot name ``mylib`` before importing it.

The library's domain name is also accepted, and is equivalent as long as the
import has already happened:

.. code-block:: python

   import mylib   # required first: this is what registers the domain

   coheriq.enable_engine("mylib", "fast-engine")

Reach for the string form only where the module form is unavailable — for
instance in a single file that defines a domain and enables an engine for it,
since such a file cannot import itself.  In practice this means demonstrations
and notebooks rather than application code.

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
