# This code is a Qiskit project.
#
# (C) Copyright IBM 2026.
#
# This code is licensed under the Apache License, Version 2.0. You may
# obtain a copy of this license in the LICENSE.txt file in the root directory
# of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
#
# Any modifications or derivative works of this code must retain this
# copyright notice, and modified files need to carry a notice indicating
# that they have been altered from the originals.

import importlib
import sys
import warnings
from importlib.metadata import EntryPoint
from unittest import mock

import coheriq
import coheriq.domain as domain_module
import pytest
from coheriq import (
    REFERENCE,
    AccelerationDomain,
    AccelerationEngine,
    CoheriqDomainError,
    CoheriqDomainNotFoundError,
    CoheriqDomainWarning,
    CoheriqEngineError,
    CoheriqEngineNotFoundError,
    CoheriqLibraryError,
    CoheriqUserError,
    CoheriqWarning,
    activation,
    active_engine,
    available_engines,
    enable_engine,
)


def _fake_entry_points(requested_group, group, names):
    """Return fake entry points for ``group``, or none for any other group."""
    if requested_group != group:
        return ()
    return tuple(EntryPoint(name=name, value="does.not:exist", group=group) for name in names)


def f():
    return 42


def g(n=42):
    return 2 * n


def h(a=0, b=1):
    return 2 * a + b


@pytest.fixture
def domain_name():
    domain_name = "foo"
    domain = AccelerationDomain(domain_name)
    domain.materialize()
    return domain_name


class TestDomainConstruction:
    def test_conflicting_names(self):
        AccelerationDomain("foo")
        with pytest.raises(CoheriqDomainError):
            AccelerationDomain("foo")

    def test_empty_name(self):
        with pytest.raises(CoheriqDomainError):
            AccelerationDomain("")

    def test_none_name(self):
        with pytest.raises(CoheriqDomainError):
            AccelerationDomain(None)

    def test_nonstring_name(self):
        with pytest.raises(CoheriqDomainError):
            AccelerationDomain(1)

    def test_double_materialize(self):
        domain = AccelerationDomain("foo")
        domain.materialize()
        with pytest.raises(CoheriqDomainError):
            domain.materialize()

    def test_candidate_after_materialize(self):
        domain = AccelerationDomain("foo")
        domain.materialize()
        with pytest.raises(CoheriqDomainError):
            domain.acceleration_candidate(f)

    def test_call_before_materialize(self):
        domain = AccelerationDomain("foo")
        wrapped_f = domain.acceleration_candidate(f)
        with pytest.raises(CoheriqDomainError):
            wrapped_f()

    def test_default_implementation(self):
        domain = AccelerationDomain("foo")
        wrapped_f = domain.acceleration_candidate(f)
        domain.materialize()
        assert wrapped_f() == f()

    def test_known_domains(self):
        # Construct out of alphabetical order to test sorting.
        AccelerationDomain("foo")
        AccelerationDomain("bar")

        assert coheriq.known_domains() == ("bar", "foo")


class TestEngineConstruction:
    def test_conflicting_names(self, domain_name):
        AccelerationEngine(domain_name, "bar")
        with pytest.raises(CoheriqEngineError):
            AccelerationEngine(domain_name, "bar")

    def test_empty_name(self, domain_name):
        with pytest.raises(CoheriqEngineError):
            AccelerationEngine(domain_name, "")

    def test_none_name(self, domain_name):
        with pytest.raises(CoheriqEngineError):
            AccelerationEngine(domain_name, None)

    def test_nonstring_name(self, domain_name):
        with pytest.raises(CoheriqEngineError):
            AccelerationEngine(domain_name, 1)

    def test_double_materialize(self, domain_name):
        engine = AccelerationEngine(domain_name, "bar")
        engine.materialize()
        with pytest.raises(CoheriqEngineError):
            engine.materialize()

    def test_candidate_after_materialize(self, domain_name):
        engine = AccelerationEngine(domain_name, "bar")
        engine.materialize()
        with pytest.raises(CoheriqEngineError):
            engine.override(g)

    def test_unknown_domain_name(self, domain_name):
        with pytest.raises(CoheriqEngineError):
            AccelerationEngine(domain_name + "2", "bar")

    def test_construct_before_domain_is_materialized(self):
        # An engine inherits from its domain's class and validates overrides
        # against the domain's candidate set, so the domain must be materialized
        # first.  Previously this was unchecked and surfaced much later as a bare
        # AttributeError from materialize().
        domain = AccelerationDomain("foo")
        domain.acceleration_candidate(f)
        with pytest.raises(CoheriqEngineError, match="must be materialized"):
            AccelerationEngine("foo", "bar")

    def test_no_override_before_enabled(self):
        domain = AccelerationDomain("foo")
        wrapped_f = domain.acceleration_candidate(f)
        domain.materialize()
        engine = AccelerationEngine("foo", "bar")
        engine.override(name="f")(g)
        engine.materialize()
        assert wrapped_f() == f()

    def test_no_override_before_enabled_implicit_name(self):
        domain = AccelerationDomain("foo")
        wrapped_f = domain.acceleration_candidate(f)
        domain.materialize()
        engine = AccelerationEngine("foo", "bar")
        engine.override("f")(g)
        engine.materialize()
        assert wrapped_f() == f()


class TestEngineEnablement:
    def test_override(self):
        domain = AccelerationDomain("foo")
        wrapped_f = domain.acceleration_candidate(f)
        domain.materialize()
        engine = AccelerationEngine("foo", "bar")
        engine.override(name="f")(g)
        engine.materialize()
        enable_engine(domain, "bar")
        assert wrapped_f() == g()

    def test_override_implicit_name(self):
        domain = AccelerationDomain("foo")
        wrapped_f = domain.acceleration_candidate(f)
        domain.materialize()
        engine = AccelerationEngine("foo", "bar")
        engine.override("f")(g)
        engine.materialize()
        enable_engine(domain, "bar")
        assert wrapped_f() == g()

    def test_environment_variable_activation(self, monkeypatch):
        domain = AccelerationDomain("foo", env_prefix="FOO")
        wrapped_f = domain.acceleration_candidate(f)
        domain.materialize()
        engine = AccelerationEngine("foo", "bar")
        engine.override(name="f")(g)
        engine.materialize()
        monkeypatch.setenv("FOO_ENGINE", "bar")
        assert wrapped_f() == g()

    def test_environment_variable_nonactivation(self):
        domain = AccelerationDomain("foo", env_prefix="FOO")
        wrapped_f = domain.acceleration_candidate(f)
        domain.materialize()
        engine = AccelerationEngine("foo", "bar")
        engine.override(name="f")(g)
        engine.materialize()
        assert wrapped_f() == f()

    def test_explicit_activation_of_unknown_engine(self):
        domain = AccelerationDomain("foo", env_prefix="FOO")
        domain.materialize()
        with pytest.raises(CoheriqEngineNotFoundError):
            enable_engine(domain, "baz")

    def test_implicit_activation_of_unknown_engine(self, monkeypatch):
        domain = AccelerationDomain("foo", env_prefix="FOO")
        wrapped_f = domain.acceleration_candidate(f)
        domain.materialize()
        monkeypatch.setenv("FOO_ENGINE", "baz")
        with pytest.raises(CoheriqEngineNotFoundError):
            wrapped_f()

    def test_explicit_activation_takes_precedence(self, monkeypatch):
        # Domain
        domain = AccelerationDomain("foo", env_prefix="FOO")
        wrapped_f = domain.acceleration_candidate(f)
        domain.materialize()
        # bar engine
        engine1 = AccelerationEngine("foo", "bar")
        engine1.override(name="f")(g)
        engine1.materialize()
        # baz engine
        engine2 = AccelerationEngine("foo", "baz")
        engine2.override(name="f")(h)
        engine2.materialize()
        # test activation
        monkeypatch.setenv("FOO_ENGINE", "bar")
        enable_engine(domain, "baz")
        assert wrapped_f() == h() != g()

    def test_enable_engine_holds_both_locks(self):
        # ``_enable_engine_low_level`` mutates state on both the domain and the
        # engine, so both locks must be held while it runs.  Observe this from
        # inside the critical section by patching it.
        domain = AccelerationDomain("foo")
        domain.acceleration_candidate(f)
        domain.materialize()
        engine = AccelerationEngine("foo", "bar")
        engine.override(name="f")(g)
        engine.materialize()

        observed = {}
        original = activation._enable_engine_low_level

        def held(lock):
            # ``acquire(blocking=False)`` fails iff the lock is already held.
            if lock.acquire(blocking=False):
                lock.release()
                return False
            return True

        def spy(domain_, engine_):
            observed["domain"] = held(domain_._lock)
            observed["engine"] = held(engine_._lock)
            return original(domain_, engine_)

        with mock.patch.object(activation, "_enable_engine_low_level", spy):
            enable_engine(domain, "bar")

        assert observed == {"domain": True, "engine": True}


class TestAvailableEngines:
    def test_no_engines(self):
        domain = AccelerationDomain("foo")
        domain.materialize()
        assert available_engines(domain) == (REFERENCE,)

    def test_registered_engines_sorted(self):
        domain = AccelerationDomain("foo")
        domain.materialize()
        for name in ("bar", "quux", "baz"):
            AccelerationEngine("foo", name).materialize()
        assert available_engines(domain) == (REFERENCE, "bar", "baz", "quux")

    def test_accepts_domain_name(self, domain_name):
        AccelerationEngine(domain_name, "bar").materialize()
        assert available_engines(domain_name) == (REFERENCE, "bar")

    def test_unknown_domain_name(self):
        with pytest.raises(CoheriqDomainNotFoundError):
            available_engines("nonexistent")

    def test_lists_engines_before_materialize(self):
        # An engine is registered at construction, so it is reportable even
        # before it has been materialized.
        domain = AccelerationDomain("foo")
        domain.materialize()
        AccelerationEngine("foo", "bar")
        assert available_engines(domain) == (REFERENCE, "bar")

    def test_includes_unimported_entry_points(self, monkeypatch):
        domain = AccelerationDomain("foo")
        domain.materialize()
        AccelerationEngine("foo", "bar").materialize()
        monkeypatch.setattr(
            activation,
            "entry_points",
            lambda group: _fake_entry_points(group, "coheriq.engines.foo", ["plugin"]),
        )
        assert available_engines(domain) == (REFERENCE, "bar", "plugin")

    def test_entry_point_does_not_duplicate_registered_engine(self, monkeypatch):
        domain = AccelerationDomain("foo")
        domain.materialize()
        AccelerationEngine("foo", "bar").materialize()
        monkeypatch.setattr(
            activation,
            "entry_points",
            lambda group: _fake_entry_points(group, "coheriq.engines.foo", ["bar"]),
        )
        assert available_engines(domain) == (REFERENCE, "bar")

    def test_ignores_other_domains_entry_points(self, monkeypatch):
        domain = AccelerationDomain("foo")
        domain.materialize()
        monkeypatch.setattr(
            activation,
            "entry_points",
            lambda group: _fake_entry_points(group, "coheriq.engines.other", ["plugin"]),
        )
        assert available_engines(domain) == (REFERENCE,)

    def test_does_not_resolve_implementation(self):
        # Introspection must not freeze the domain: an engine can still be
        # enabled afterwards.
        domain = AccelerationDomain("foo")
        wrapped_f = domain.acceleration_candidate(f)
        domain.materialize()
        engine = AccelerationEngine("foo", "bar")
        engine.override(name="f")(g)
        engine.materialize()
        available_engines(domain)
        enable_engine(domain, "bar")
        assert wrapped_f() == g()


class TestActiveEngine:
    def test_none_before_resolution(self):
        # None means "not decided yet" -- an engine can still be enabled.
        domain = AccelerationDomain("foo")
        domain.materialize()
        assert active_engine(domain) is None

    def test_none_before_materialization(self):
        domain = AccelerationDomain("foo")
        assert active_engine(domain) is None

    def test_reference_when_frozen_on_reference_impl(self):
        # Resolving to the domain's own implementation is a decision, so it is
        # reported as REFERENCE rather than sharing None with the undecided state.
        domain = AccelerationDomain("foo")
        wrapped_f = domain.acceleration_candidate(f)
        domain.materialize()
        assert wrapped_f() == f()
        assert active_engine(domain) == REFERENCE

    def test_reference_is_distinct_from_none(self):
        domain = AccelerationDomain("foo")
        wrapped_f = domain.acceleration_candidate(f)
        domain.materialize()
        assert active_engine(domain) is None
        assert wrapped_f() == f()
        assert active_engine(domain) is not None
        assert active_engine(domain) == REFERENCE

    def test_reference_constant_value(self):
        assert REFERENCE == "reference"

    def test_returns_enabled_engine_name(self):
        domain = AccelerationDomain("foo")
        domain.acceleration_candidate(f)
        domain.materialize()
        engine = AccelerationEngine("foo", "bar")
        engine.override(name="f")(g)
        engine.materialize()
        enable_engine(domain, "bar")
        assert active_engine(domain) == "bar"

    def test_reports_the_enabled_engine_among_several(self):
        domain = AccelerationDomain("foo")
        domain.acceleration_candidate(f)
        domain.materialize()
        for name, impl in (("bar", g), ("baz", h)):
            engine = AccelerationEngine("foo", name)
            engine.override(name="f")(impl)
            engine.materialize()
        enable_engine(domain, "baz")
        assert active_engine(domain) == "baz"

    def test_accepts_domain_name(self, domain_name):
        assert active_engine(domain_name) is None

    def test_unknown_domain_name(self):
        with pytest.raises(CoheriqDomainNotFoundError):
            active_engine("nonexistent")

    def test_reflects_environment_variable_activation(self, monkeypatch):
        domain = AccelerationDomain("foo", env_prefix="FOO")
        wrapped_f = domain.acceleration_candidate(f)
        domain.materialize()
        engine = AccelerationEngine("foo", "bar")
        engine.override(name="f")(g)
        engine.materialize()
        monkeypatch.setenv("FOO_ENGINE", "bar")
        assert wrapped_f() == g()
        assert active_engine(domain) == "bar"

    def test_reference_when_env_var_is_empty(self, monkeypatch):
        domain = AccelerationDomain("foo", env_prefix="FOO")
        wrapped_f = domain.acceleration_candidate(f)
        domain.materialize()
        monkeypatch.setenv("FOO_ENGINE", "")
        assert wrapped_f() == f()
        assert active_engine(domain) == REFERENCE

    def test_does_not_resolve_implementation(self):
        # Asking what is active must not commit the domain to an answer; an
        # engine can still be enabled afterwards.
        domain = AccelerationDomain("foo")
        wrapped_f = domain.acceleration_candidate(f)
        domain.materialize()
        engine = AccelerationEngine("foo", "bar")
        engine.override(name="f")(g)
        engine.materialize()
        assert active_engine(domain) is None
        enable_engine(domain, "bar")
        assert wrapped_f() == g()
        assert active_engine(domain) == "bar"

    def test_repeated_calls_do_not_freeze(self):
        domain = AccelerationDomain("foo")
        wrapped_f = domain.acceleration_candidate(f)
        domain.materialize()
        engine = AccelerationEngine("foo", "bar")
        engine.override(name="f")(g)
        engine.materialize()
        for _ in range(3):
            assert active_engine(domain) is None
        enable_engine(domain, "bar")
        assert wrapped_f() == g()


class TestEnableReference:
    def test_pins_reference_implementation(self):
        domain = AccelerationDomain("foo")
        wrapped_f = domain.acceleration_candidate(f)
        domain.materialize()
        enable_engine(domain, REFERENCE)
        assert wrapped_f() == f()
        assert active_engine(domain) == REFERENCE

    def test_accepts_the_literal_string(self):
        domain = AccelerationDomain("foo")
        domain.acceleration_candidate(f)
        domain.materialize()
        enable_engine(domain, "reference")
        assert active_engine(domain) == REFERENCE

    def test_accepts_domain_name(self, domain_name):
        enable_engine(domain_name, REFERENCE)
        assert active_engine(domain_name) == REFERENCE

    def test_overrides_environment_variable(self, monkeypatch):
        # The whole point of enabling the reference implementation explicitly:
        # an explicit call beats the environment, which silence cannot do.
        domain = AccelerationDomain("foo", env_prefix="FOO")
        wrapped_f = domain.acceleration_candidate(f)
        domain.materialize()
        engine = AccelerationEngine("foo", "bar")
        engine.override(name="f")(g)
        engine.materialize()
        monkeypatch.setenv("FOO_ENGINE", "bar")
        enable_engine(domain, REFERENCE)
        assert wrapped_f() == f() != g()
        assert active_engine(domain) == REFERENCE

    def test_forecloses_other_engines(self):
        domain = AccelerationDomain("foo")
        domain.acceleration_candidate(f)
        domain.materialize()
        engine = AccelerationEngine("foo", "bar")
        engine.override(name="f")(g)
        engine.materialize()
        enable_engine(domain, REFERENCE)
        with pytest.raises(CoheriqDomainError):
            enable_engine(domain, "bar")

    def test_is_idempotent(self):
        domain = AccelerationDomain("foo")
        wrapped_f = domain.acceleration_candidate(f)
        domain.materialize()
        enable_engine(domain, REFERENCE)
        enable_engine(domain, REFERENCE)
        assert wrapped_f() == f()

    def test_idempotent_after_implicit_resolution(self):
        # Already frozen on the reference implementation by a call, rather than
        # by an explicit enable.
        domain = AccelerationDomain("foo")
        wrapped_f = domain.acceleration_candidate(f)
        domain.materialize()
        assert wrapped_f() == f()
        enable_engine(domain, REFERENCE)
        assert active_engine(domain) == REFERENCE

    def test_rejected_after_an_engine_is_enabled(self):
        # It pins the reference implementation; it is not a reset.
        domain = AccelerationDomain("foo")
        domain.acceleration_candidate(f)
        domain.materialize()
        engine = AccelerationEngine("foo", "bar")
        engine.override(name="f")(g)
        engine.materialize()
        enable_engine(domain, "bar")
        with pytest.raises(CoheriqDomainError):
            enable_engine(domain, REFERENCE)
        assert active_engine(domain) == "bar"

    def test_rejected_before_materialize(self):
        domain = AccelerationDomain("foo")
        domain.acceleration_candidate(f)
        with pytest.raises(CoheriqDomainError):
            enable_engine(domain, REFERENCE)

    def test_every_available_name_is_enableable(self):
        # The contract available_engines() advertises: everything it lists can be
        # passed to enable_engine().  Checked for the reference entry, which is
        # the one with no registry entry behind it.
        domain = AccelerationDomain("foo")
        domain.acceleration_candidate(f)
        domain.materialize()
        assert REFERENCE in available_engines(domain)
        enable_engine(domain, REFERENCE)


class TestReservedEngineNames:
    def test_reference_rejected_as_engine_name(self):
        AccelerationDomain("foo").materialize()
        with pytest.raises(CoheriqEngineError, match="reserved"):
            AccelerationEngine("foo", REFERENCE)

    def test_reference_string_rejected_as_engine_name(self):
        AccelerationDomain("foo").materialize()
        with pytest.raises(CoheriqEngineError, match="reserved"):
            AccelerationEngine("foo", "reference")

    def test_reserved_prefix_rejected_as_engine_name(self):
        # The whole prefix is reserved, not just REFERENCE itself, so that a
        # name added under it later is not a compatibility break for an engine
        # that had taken it.
        AccelerationDomain("foo").materialize()
        for name in ("reference2", "reference-v2", "references"):
            with pytest.raises(CoheriqEngineError, match="reserved"):
                AccelerationEngine("foo", name)

    def test_reserved_name_check_is_case_sensitive(self):
        # The prefix is matched case-sensitively, as names are everywhere else
        # they are looked up.
        domain = AccelerationDomain("foo")
        domain.acceleration_candidate(f)
        domain.materialize()
        engine = AccelerationEngine("foo", "Reference")
        engine.override(name="f")(g)
        engine.materialize()
        enable_engine(domain, "Reference")
        assert active_engine(domain) == "Reference"

    def test_reference_is_reported_as_available(self):
        domain = AccelerationDomain("foo")
        domain.materialize()
        assert available_engines(domain) == (REFERENCE,)

    def test_reference_is_listed_first(self):
        # Ahead of names that would sort before it alphabetically.
        domain = AccelerationDomain("foo")
        domain.materialize()
        for name in ("aaa", "zzz"):
            AccelerationEngine("foo", name).materialize()
        assert available_engines(domain) == (REFERENCE, "aaa", "zzz")

    def test_available_engines_never_empty(self):
        domain = AccelerationDomain("foo")
        domain.materialize()
        assert available_engines(domain)


class TestEngineBasicInheritance:
    pass


class TestEngineDiamondInheritance:
    pass


# FIXME:
# - ensure that multiple domains don't interfere


class TestDomainNameConvention:
    """A domain's name should be the ``__name__`` of the package it belongs to.

    The convention is advisory: violating it warns and nothing more, because a
    domain defined in a script, a notebook, or a test has no package to name.
    """

    def test_warns_when_name_is_not_an_importable_module(self):
        with pytest.warns(CoheriqDomainWarning, match="does not name an importable module"):
            AccelerationDomain("not_an_importable_module_xyz")

    def test_no_warning_when_name_is_an_importable_module(self):
        # ``coheriq`` is necessarily importable, since this test imports it.
        with warnings.catch_warnings():
            # "error" overrides the suite-wide ignore, so a warning here fails.
            warnings.simplefilter("error", CoheriqWarning)
            AccelerationDomain("coheriq")

    def test_findability_not_prior_import_is_the_criterion(self):
        # A domain is normally constructed while its own package is still being
        # imported, so requiring prior import would warn on every correctly
        # named domain.  Findability is what the convention needs.
        name = "coheriq.activation"
        assert name in sys.modules
        del sys.modules[name]
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", CoheriqWarning)
                AccelerationDomain(name)
        finally:
            importlib.import_module(name)

    @pytest.mark.parametrize("name", ["my lib", "foo..bar", ".foo", "foo.", "foo-bar"])
    def test_warns_for_a_name_that_cannot_be_a_module(self, name):
        # These reach find_spec, which raises for some of them rather than
        # returning None.  Reaching the warning at all is what is under test:
        # nothing may escape the lookup.
        with pytest.warns(CoheriqDomainWarning):
            AccelerationDomain(name)

    def test_empty_name_still_raises(self):
        # The pre-existing error takes precedence over the convention warning.
        with pytest.raises(CoheriqDomainError, match="cannot be empty"):
            AccelerationDomain("")

    def test_warning_is_filterable_through_the_hierarchy(self):
        for category in (CoheriqDomainWarning, CoheriqWarning, UserWarning):
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always", CoheriqDomainWarning)
                warnings.simplefilter("ignore", category)
                AccelerationDomain(f"unimportable_{category.__name__}")
            assert not caught, f"not suppressed by filtering on {category.__name__}"

    def test_warning_derives_from_user_warning(self):
        assert issubclass(CoheriqDomainWarning, CoheriqWarning)
        assert issubclass(CoheriqWarning, UserWarning)

    def test_a_finder_that_raises_does_not_break_construction(self):
        # The check only ever informs a warning, so a misbehaving finder must
        # not be allowed to propagate out of AccelerationDomain().
        with (
            mock.patch.object(
                domain_module.importlib.util, "find_spec", side_effect=ImportError("boom")
            ),
            pytest.warns(CoheriqDomainWarning),
        ):
            domain = AccelerationDomain("coheriq")
        assert domain._name == "coheriq"


class TestDomainAsModule:
    """A module may stand in for the domain it is named after."""

    @pytest.fixture
    def coheriq_domain(self):
        domain = AccelerationDomain("coheriq")
        domain.materialize()
        return domain

    def test_enable_engine_accepts_a_module(self, coheriq_domain):
        AccelerationEngine(coheriq_domain, "fast").materialize()
        enable_engine(coheriq, "fast")
        assert active_engine(coheriq) == "fast"

    def test_available_engines_accepts_a_module(self, coheriq_domain):
        AccelerationEngine(coheriq_domain, "fast").materialize()
        assert available_engines(coheriq) == (REFERENCE, "fast")

    def test_active_engine_accepts_a_module(self, coheriq_domain):
        assert active_engine(coheriq_domain) is None
        enable_engine(coheriq, REFERENCE)
        assert active_engine(coheriq) == REFERENCE

    def test_engine_construction_accepts_a_module(self, coheriq_domain):
        engine = AccelerationEngine(coheriq, "fast")
        assert engine._domain is coheriq_domain

    def test_module_and_name_resolve_to_the_same_domain(self, coheriq_domain):
        assert domain_module._resolve_domain(coheriq, CoheriqDomainNotFoundError)[0] is (
            coheriq_domain
        )
        assert domain_module._resolve_domain("coheriq", CoheriqDomainNotFoundError)[0] is (
            coheriq_domain
        )

    def test_a_submodule_does_not_resolve_to_its_parent(self, coheriq_domain):
        # Resolution is by name only.  A domain may be named for any importable
        # module, so a submodule standing in for its parent would be a guess.
        resolved, _ = domain_module._resolve_domain(coheriq, CoheriqDomainNotFoundError)
        assert resolved is coheriq_domain
        with pytest.raises(CoheriqDomainNotFoundError, match="defines no domain of that name"):
            enable_engine(activation, "fast")

    @pytest.mark.parametrize("bad", [42, None, [], f])
    def test_a_non_module_non_name_raises_type_error(self, bad):
        with pytest.raises(TypeError, match="must be an AccelerationDomain, a module"):
            enable_engine(bad, "fast")

    def test_engine_construction_shares_the_lookup_diagnostics(self, coheriq_domain):
        # Engine construction and enable_engine resolve the domain through the
        # same helper, so an engine author gets the same explanation a user does.
        name = "coheriq.activation"
        assert name in sys.modules
        del sys.modules[name]
        try:
            with pytest.raises(CoheriqEngineError, match="has not been imported"):
                AccelerationEngine(name, "fast")
        finally:
            importlib.import_module(name)
        with pytest.raises(CoheriqEngineError, match=f"Registered domains: {coheriq_domain._name}"):
            AccelerationEngine("cohriq", "fast")

    def test_engine_and_user_errors_stay_classified_differently(self, coheriq_domain):
        # Shared resolution must not collapse the two branches of the hierarchy:
        # an engine naming a missing domain is library misuse, a user doing so is
        # a user error.
        missing = coheriq_domain._name + "-nope"
        with pytest.raises(CoheriqLibraryError):
            AccelerationEngine(missing, "fast")
        with pytest.raises(CoheriqUserError):
            enable_engine(missing, "fast")

    def test_engine_construction_rejects_a_non_module_non_name(self, coheriq_domain):
        assert coheriq_domain._name == "coheriq"
        # Unlike a missing domain, an argument that cannot name one at all is a
        # TypeError whichever call site reports it.
        with pytest.raises(TypeError, match="must be an AccelerationDomain, a module"):
            AccelerationEngine(42, "fast")


class TestDomainNotFoundMessage:
    """The failure explains import order, which is the overwhelmingly likely cause."""

    def test_importable_but_unimported_name_suggests_importing_it(self):
        name = "coheriq.activation"
        assert name in sys.modules
        del sys.modules[name]
        try:
            with pytest.raises(CoheriqDomainNotFoundError, match="has not been imported"):
                enable_engine(name, "fast")
        finally:
            importlib.import_module(name)

    def test_message_mentions_registered_domains(self, domain_name):
        with pytest.raises(CoheriqDomainNotFoundError, match=f"Registered domains: {domain_name}"):
            enable_engine(domain_name[:-1], "fast")

    def test_message_when_nothing_is_registered(self):
        with pytest.raises(CoheriqDomainNotFoundError, match="no domains are registered at all"):
            enable_engine("nonexistent_package_xyz", "fast")

    def test_imported_module_that_defines_no_domain(self):
        with pytest.raises(CoheriqDomainNotFoundError, match="defines no domain of that name"):
            enable_engine(warnings, "fast")
