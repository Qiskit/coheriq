##########
Design FAQ
##########

This page explains *why* Coheriq is built the way it is. Where a decision had
plausible alternatives, it records what they were and why they were not chosen.
It is aimed at people evaluating the framework, contributing to it, or simply
wondering "why not do it *that* way instead?"

The :doc:`conceptual overview <overview>` introduces the vocabulary
(*domain*, *engine*, *candidate*, *activation*) used throughout.


The dispatch mechanism
======================

Why substitute whole coherent units instead of overriding individual functions?
--------------------------------------------------------------------------------

A tempting alternative is to let an engine replace acceleration candidates one
function at a time, mixing accelerated and default implementations freely. Coheriq
deliberately does not work that way: an engine substitutes a **coherent unit** of
behavior. What you are really selecting is a *policy* for how a body of work is
carried out, not a patch to a single mechanism. Several things follow from that
distinction:

- **Invariants travel together.** A function rarely stands alone. It assumes a
  particular data representation, a device or memory model, an ordering, some
  hidden state. Overriding just the function replaces one leaf while the tree of
  assumptions around it stays implicit and unchanged. Substituting the whole unit
  replaces the *bundle of invariants*, not merely a line of code.
- **Atomicity — no half-accelerated limbo.** If some calls dispatched to the
  engine and others to the default, a program could end up in a
  *half-accelerated limbo state*: mixing representations, hopping needlessly
  between host and device, or producing subtly wrong results. Whole-unit
  substitution is consistent by construction — either the engine's world is in
  effect, or it is not.
- **Composition without ambiguity.** Independent per-function overrides create
  combinatorial ambiguity: if two parties each override some functions, which
  wins, and in what order? Substituting whole units lets composition be resolved
  by a single, well-defined method-resolution order (see
  :ref:`the question on type() and inheritance <faq-type-inheritance>`) rather
  than an ad-hoc runtime blend.
- **State needs an owner.** Accelerated code carries state — device handles,
  memory pools, scratch buffers, kernel caches. Threading that state through a
  collection of overridden free functions pushes it into hidden globals and
  invites threading and multi-process hazards. A coherent unit — an engine
  *class* — has a natural place to own it.
- **Debugging stays stateless.** With one coherent engine active per process,
  the question behind almost any misbehavior collapses to "which engine is
  active?" — a single fact you can read off directly. Per-function overrides
  instead force *temporal* debugging: reconstructing which override was in place
  when, and whether anything clobbered it along the way.

Why a decorator rather than a central interface class?
------------------------------------------------------

A library marks acceleration candidates with a decorator
(``@domain.acceleration_candidate``) rather than by declaring a formal
interface — an abstract base class or a ``Protocol`` — that engines must
implement.

The decorator approach keeps the API surface lightweight and requires no
central coordination. A library author can mark a new candidate with a single
line, anywhere, without touching a shared interface definition. If marking a
patchable point were expensive — say, defining a class or adding to a central
registry each time — authors would do it sparingly, and the framework would be
less useful.

**Alternatives considered:**

- **Abstract base classes (**\ ``abc.ABC``\ **).** Not viable in the general
  case: classes implemented in compiled extensions (for example, nanobind
  classes) cannot derive from Python-native base classes, so an ABC-based
  contract would exclude exactly the accelerated implementations Coheriq exists
  to support.
- **Typing** ``Protocol``\ **.** Gives static-typing benefits but does nothing
  for *runtime* dispatch or construction-time replacement, which is the whole
  point. A ``Protocol`` describes a shape; it does not swap an implementation.

Why not swap function bodies with ``f.__code__`` replacement?
-------------------------------------------------------------

One way to "override" a function would be to reach in and replace its
``__code__`` object. Coheriq does not do this. Compiled functions (again, think
nanobind) would have to be wrapped in Python-level shims for this to work,
adding a layer of indirection and reducing transparency. It is also fragile
around introspection and debugging — the function you inspect is no longer the
function that runs. Dispatching through a wrapper that resolves to the active
implementation is simpler and keeps the real callable intact.

.. _faq-type-inheritance:

Why use ``type()`` and real inheritance under the hood?
-------------------------------------------------------

When a domain materializes, Coheriq builds a class from its default
implementations using :func:`type`. Each engine builds its own class that
inherits from that domain class. This is a deliberate choice: because engines
are ordinary Python classes, **composing engines is just Python multiple
inheritance**, resolved by the standard method-resolution order (MRO).

The payoff is that two independently developed engines — say one that
accelerates function ``A`` and another that accelerates function ``B`` — can be
combined into a third engine that delivers both accelerations, with almost no
supporting code. Reusing
Python's own inheritance machinery means we did not have to invent (or ask
users to learn) a bespoke composition model.

Why not use metaclasses for class overrides?
---------------------------------------------

Replacing a marked class with an accelerated one via a metaclass is possible,
but it introduces significantly higher implementation complexity for unclear
practical benefit compared with the decorator-plus-\ ``type()`` approach.
Construction-time dispatch through a wrapper achieves the same user-visible
outcome — the marked name produces the active implementation's instances —
without the conceptual overhead of a metaclass.

Is this a novel architecture, or over-engineered?
--------------------------------------------------

Neither. The core pattern — a plain function-and-class API on the surface, a
stateful and swappable implementation underneath — is one the major numerical
libraries already use. Coheriq's contribution is to make that structure
*explicit and reusable* rather than bespoke to one library.

- **NumPy** presents pure-looking functions; ``numpy.dot`` delegates to a BLAS
  library (OpenBLAS, MKL, Accelerate). Which BLAS runs is selected out of band —
  usually fixed when NumPy is built or installed, and switchable at runtime only
  through a dedicated mechanism such as a FlexiBLAS-linked build. Either way, you
  do not change it by monkey-patching ``numpy.dot`` itself.
- **PyTorch** exposes functions that are façades over a stateful backend.
  Operations are routed through a dispatcher keyed by, among other things, a
  device/backend (CPU, CUDA, …) rather than by overriding operators one at a
  time, and the CUDA runtime, memory pools, and streams are process-level state.

The common thread is that the user-facing function is a *façade* over an
implementation that is selected out of band and owns real state, not something
callers replace piece by piece. That is exactly the seam Coheriq formalizes.

Where these libraries differ from Coheriq is in the *level of abstraction* they
operate at, and the granularity of selection follows from it. PyTorch and JAX
work at a low level — arrays, operations, kernels — and there per-value backend
placement is exactly right: JAX lets you place arrays and computations on
specific devices with ``jax.device_put`` and ``jit``'s ``device`` argument, and
PyTorch tensors each carry their own device. When the unit is a single array, you
genuinely want one on this GPU and another on that one.

Coheriq sits a level up. It targets **high-level functionality** — a whole
algorithm or capability whose implementation is a coherent backend of its own,
with its own data representations, execution model, and invariants. At that
granularity there is a full backend to swap as a unit, and choosing one
implementation for the whole process is the natural fit rather than a
compromise (see :ref:`the question on process-global activation
<faq-process-global>`). Per-call selection at this level would only reintroduce
the mixed-representation hazard the design exists to avoid. So Coheriq is not
reinventing something exotic — it takes the well-worn
façade-over-swappable-backend pattern and applies it where the swappable unit is
large and coherent enough that a single, one-time choice is what you want.


The activation contract
========================

Coheriq's rules for activating an engine are deliberately restrictive. Each
restriction removes a class of failure mode rather than limiting anything a
user realistically needs to do. The guiding principle is *as simple as
possible, but no simpler.*

Why must an engine be activated before first use?
-------------------------------------------------

Activation must happen before any marked function or class is used. After first
use, the choice of implementation is locked in.

The reason is data consistency. An engine may replace not only functions but
also the *data structures* a library produces and consumes, choosing a
representation better suited to acceleration. If a program built some objects
with the default representation and then switched engines, later code could
receive a mix of default-native and accelerated representations — an
inconsistent state that is difficult to reason about and easy to get wrong.
Requiring activation up front makes the data layout coherent for the entire
lifetime of the process.

Why is activation one-way, with no disable and no reset?
--------------------------------------------------------

Once an engine is enabled, it cannot be swapped for a different one or turned
off, and there is no reset in the public API. This follows from the
before-first-use rule: allowing a later switch would reintroduce exactly the
inconsistent-state failure mode that rule exists to prevent. One-way activation
eliminates a whole category of "how did I get into this state?" bugs and does
not meaningfully restrict what a user can accomplish — to use a different
engine, start a new process.

.. _faq-process-global:

Why is activation process-global rather than per-call or scoped?
----------------------------------------------------------------

Activation applies to the entire process, not to a call, a thread, or a
``with`` block. It is unlikely that different parts of the same program
genuinely need different implementations of the same library, and a single
global choice keeps the model simple and predictable. This also mirrors how
related execution configuration is conventionally handled (for example, the
number of BLAS or OpenMP threads is typically set once per process, before
work begins).

There is a designed escape hatch for the rare case where global configuration
is genuinely too coarse: an API may accept an opaque ``execution_context``
argument, allowing multiple execution strategies to coexist without mutating
global state. That mechanism is layered *on top of* the simple global model
rather than replacing it.

Why is re-enabling the same engine allowed, when switching engines is not?
--------------------------------------------------------------------------

Enabling the engine that is already active is treated as an idempotent no-op,
not an error. This is purely a usability decision: startup code sometimes runs
more than once, and there is no good reason to punish a redundant but harmless
call. Enabling a *different* engine after one is active is the operation that
would break the consistency guarantees, so that remains an error.

Why is enabling explicitly in code preferred over the environment variable?
---------------------------------------------------------------------------

An engine can be selected either by an explicit ``enable_engine()`` call or,
when the library opts in, by an environment variable. When both are present,
the explicit call wins. This lets a script pin the engine it depends on
regardless of the surrounding environment, while still letting users who have
*not* pinned anything select an engine from the outside without editing code.


API shape
=========

Why is materializing an explicit step rather than automatic?
------------------------------------------------------------

Both a domain and an engine require an explicit call to finish construction
before they can be used. This is not automatic-on-first-use for several
reasons that reinforce one another:

- **A clear error boundary.** The explicit call defines exactly when the set of
  candidates (or overrides) is closed. Marking something too late becomes a
  crisp, early error at a well-defined point, rather than surprising behavior
  discovered much later.
- **Control over import timing.** Finishing construction requires that every
  module carrying a decorator has already been imported. Making this an
  explicit step puts the author in control of import order — which matters for
  keeping heavyweight dependencies from being imported eagerly.
- **A well-defined base for composition.** The moment of materialization is
  when the domain's class exists and is fixed, giving engines a stable base
  class to inherit from at a known point in time.


Why is ``enable_engine`` a free function rather than a method?
--------------------------------------------------------------

Activation is a free function, ``coheriq.enable_engine(domain, engine)``, where
``domain`` is the library's domain name (or an
:class:`~coheriq.AccelerationDomain` object). An earlier design made it a method
on the domain, ``domain.enable_engine(name)``, which a library was expected to
re-export so users could write ``mylib.enable_engine("fast")``. The method form
has one genuine advantage — the domain is implicit, so calling code names only
the library — but three considerations outweighed it:

- **The method form forced an internal import cycle.** The activation logic
  depends on both :class:`~coheriq.AccelerationDomain` and
  :class:`~coheriq.AccelerationEngine`, so it lives in a module that imports
  both. When ``enable_engine`` was a *method*, the domain module had to reach
  back into that activation module — a cycle survivable only through a
  function-local import with a ``pylint`` suppression. Moving the function into
  the activation layer makes the dependency graph a clean one-way DAG.
- **The re-export burden would grow with the API.** ``enable_engine`` is not
  expected to stay the only such operation; siblings like ``available_engines``
  and ``active_engine`` are anticipated. With the method form, every library
  author would have to re-export each one and keep ``__all__`` in sync — and the
  bound-method re-export trick does not even work cleanly for a property-style
  accessor. Free functions give every library the whole (growing) surface with
  no per-function boilerplate and identical behavior across libraries.
- **It lowers the barrier to adopting Coheriq.** Because activation lives in
  Coheriq, a library documents *nothing* about it — it can simply point users at
  Coheriq's own :doc:`user guide <guides/user-guide>`. There is no per-library
  activation surface to design, export, or document.

The cost is that user code names the domain on each call
(``coheriq.enable_engine("mylib", "fast")``) and imports ``coheriq``. The domain
name is a short, stable identifier, and the import is a single line at startup,
so the tradeoff favors the free function. A future refinement is expected to let
a library *module* stand in for its domain name, removing even that small
coupling; that is being designed separately.


Naming
======

The vocabulary was chosen with some care, because names outlive the code they
describe and shape how contributors reason about the framework. A few of the
less obvious choices:

Why ``acceleration_candidate``?
-------------------------------

The decorator names a *role and a potential*, not an outcome. At the moment a
library author writes ``@domain.acceleration_candidate``, nothing is
accelerated; the author is declaring a stable point that *may* be accelerated
later by some engine. "Candidate" captures that pending status exactly.

Names that assert a present capability were rejected for over-promising:
``supports_acceleration`` reads like a feature already delivered rather than an
opening left for one; ``accelerable`` is linguistically awkward. Names that
describe only the mechanism — ``dispatchable``, ``extension_point`` — were too
abstract to convey intent at the call site.

Why ``Engine`` rather than ``Backend`` or ``Provider``?
-------------------------------------------------------

"Engine" is the ecosystem-neutral choice, and that matters especially because
Coheriq is Qiskit-adjacent. In Qiskit, **Backend** and **Provider** are already
load-bearing terms with specific meanings (for example ``BackendV2`` and the
hardware/simulator providers behind it). Reusing either would collide with
concepts users already hold, and "Backend" additionally carries a hardware
connotation that an engine — which might be a CPU, GPU, MPI, tracing, or debug
implementation — does not warrant.

"Engine" also reads well *socially*, which is a real design consideration for an
open ecosystem: an author naturally says "I wrote an engine for CUDA," and the
sentence needs no explanation. ``AccelerationEngine`` is the explicit form, and
it pairs symmetrically with ``AccelerationDomain``.

Why ``Domain``?
---------------

A domain names *what it organizes* — a scope of acceleration candidates — rather
than what it executes. Mechanism-forward names such as ``Registry`` or
``Manager`` leak the internal data structure, and performance-implying names
such as ``Accelerator`` or ``Provider`` overstate what the object does (it
supplies no acceleration itself; it only declares the candidates). "Domain"
stays at the right layer and reads cleanly in use:
``@domain.acceleration_candidate`` says "within this acceleration domain, this
function is a candidate for acceleration."

Why "Coheriq"?
--------------

The central idea is that an implementation is substituted as one *coherent*
unit; the package name is built from that word. A slightly coined name keeps it
distinct on PyPI and — unlike a plain English term — ties the project to its
core concept without committing it to acceleration, hardware, or quantum
computing specifically. The :doc:`conceptual overview <overview>` explains the
coherent-unit idea the name refers to.


The plugin and packaging model
==============================

Why a plugin model at all, instead of just merging accelerated code upstream?
------------------------------------------------------------------------------

It is reasonable to ask why acceleration is not simply folded into the library
once it exists. Several forces make an *optional, pluggable* model at times the better
choice:

- **Specialized or non-portable requirements.** An accelerated implementation
  may need particular hardware (a GPU), a system-specific MPI build, or a
  toolchain not every user has. Making it optional means users who cannot run
  it keep a working library.
- **Ecosystem diversity.** A healthy ecosystem can have *several* engines suited to
  different environments. A decentralized model evolves faster than a
  centralized one, especially when the standard for "correct" is clear (does it
  pass the test suite?).
- **Researcher preference for the reference implementation.** Someone modifying
  the algorithm, unable to build the accelerated version, or burned by an
  unreliable one, needs the straightforward implementation to remain available.
- **Maintainer bottleneck.** Reviewing and merging a large, specialized
  acceleration pull request is slow and burdensome for library maintainers. A
  plugin model lets them focus on the library while engine authors iterate
  independently.
- **Maturity lag.** An accelerated implementation is usually more complex and
  less mature than the library. A plugin model lets early engine versions reach
  the users who can benefit, instead of holding them back until they are
  complete and bug-free.
- **Behavioral stability (Hyrum's Law).** Swapping a large portion of a
  library's implementation tends to change observable behavior across versions.
  With a plugin model, the user *chooses* when to take that change, rather than
  having it forced on them as a mandatory upgrade.

None of this prevents mature, proven acceleration from being upstreamed later.
The model also works whether an engine lives in the library's own repository or
a separate one.

Why entry points and stdlib ``importlib.metadata`` rather than an existing plugin library?
------------------------------------------------------------------------------------------

Coheriq discovers engines through Python **entry points**, read with the
standard library's ``importlib.metadata``, rather than adopting an established
plugin-management library such as stevedore.

The piece the two approaches share is *discovery*: "given a name, find and
import the right plugin from installed packages." Since Python 3.10 that is a
few lines of ``importlib.metadata``. Everything else a general plugin manager
offers — a plugin registry, lifecycle management, and a dispatch mechanism —
Coheriq already provides in a more specific form: the registry and lifecycle
*are* the domain and its state machine, activation *is* ``enable_engine``, and
dispatch is transparent (call sites do not change). Adopting a general plugin
library would mean taking on a runtime dependency and a second, overlapping
registry and error vocabulary, to reuse only its discovery step — the one part
now available for free in the standard library.

Discovery is also **lazy**: enabling an engine imports only that one engine's
module, never every declared engine. This matters because engines routinely
pull in heavy dependencies (CUDA, MPI), and a user should not pay to import an
engine they are not enabling.

Why a Python-package-level plugin system, not a C-API (``dlopen``) one?
-----------------------------------------------------------------------

The plugin boundary is a Python package. Python is the language that many target
users work in, and a package-level system aligns with existing packaging,
distribution, and dependency-management practices (PyPI, conda-forge), lowering
the barrier for contributors. Performance-critical code can still be written in
C, C++, or Rust and exposed through a Python interface — the plugin boundary
does not need to be lower than Python to accommodate that.

A plugin system at the ``dlopen`` / C-API level
would enable lower-level extensibility but sharply raises development
complexity and shifts the burden toward binary distribution, ABI
compatibility, and platform-specific concerns — fragmenting the ecosystem and
complicating installation for users.


Class replacement tradeoffs
============================

Why is it acceptable that ``isinstance``, subclassing, and ``@classmethod`` break?
----------------------------------------------------------------------------------

When a marked *class* is replaced with a callable by the ``@_supports_acceleration`` decorator, several ordinary class features stop behaving as expected:

- ``isinstance`` and ``issubclass`` checks against the marked class are not
  reliable,
- subclassing the marked class is not supported,
- ``@classmethod`` does not work (though ``@staticmethod`` does), and
- class attributes are not reliably available before instantiation.

These are acceptable because of the *intended use case*: marking classes that
act as **data containers**, where construction-time dispatch and composition
are the right tools, rather than behavioral base classes that rely on
inheritance and instance/subclass checks. A class meant to be used as a
polymorphic base should not be marked as an acceleration candidate in the first
place. Within the data-container use case, none of the lost features are ones
you would reach for.


Non-goals
=========

Some things are deliberately out of scope. Naming them is itself a design
decision — it keeps the framework small and its guarantees strong.

Reconfiguration after first use
-------------------------------

Coheriq does not support switching or disabling an engine once the library has
been used. This is the one-way activation contract above, stated as a boundary:
reconfiguration is not a missing feature, it is intentionally excluded to
preserve data-representation consistency.

It is worth being explicit about why a "reset" is not offered, because the
omission is deliberate rather than unfinished. There are three things one might
mean by resetting:

- **Logical reset** — swap the active-implementation reference back. This looks
  safe and is easy to implement, but it is a leaky illusion. Objects the old
  engine already handed out keep the old representation, so the process ends up
  mixing representations anyway — precisely the inconsistency the
  before-first-use rule exists to prevent.
- **Resource teardown** — actually free the device contexts, memory pools, and
  kernel caches an engine allocated. This is genuinely hard and risky: live
  objects may still reference freed state, and foreign runtimes (CUDA, MKL, and
  the like) manage resources outside Coheriq's control and often cannot be
  cleanly rewound.
- **Process restart** — start a fresh interpreter. It is the blunt option, but
  it is the only one that is actually reliable.

The principle this leaves us with: **reset at the Python level is a convenience;
reset at the process level is a guarantee.** Coheriq declines to ship a
convenience that cannot be made a guarantee, and directs anyone who needs a
different engine to a new process instead — which, for the HPC and MPI settings
Coheriq targets, is already the normal unit of work.

More than one engine active per domain
--------------------------------------

A domain runs at most one engine at a time. Coheriq does not support several
engines being simultaneously active for the same domain. The supported way to
get the benefit of multiple engines is to **compose them through inheritance**
into a single hybrid engine, which resolves overrides via a single, well-defined
MRO rather than an ambiguous runtime blend.

Optimizing for non-Python callers
----------------------------------

The framework optimizes the experience for Python users. Making acceleration
ergonomic from other languages is not a goal. Accelerated *implementations* may
of course be written in any language and exposed to Python; it is the
*plugin-model ergonomics* that are Python-centric.

Deciding execution policy
-------------------------

Coheriq dispatches to an implementation; it does not decide *how* that
implementation runs. Choices such as thread counts, process ranks, tiling, or
which BLAS to use are the responsibility of the engine and the user's
environment, not of Coheriq. Keeping execution policy out of the framework is
what lets the same call sites run unchanged across single-node, GPU, and
multi-process settings.
