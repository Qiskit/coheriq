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

import pytest
from coheriq import (
    AccelerationDomain,
    AccelerationEngine,
    CoheriqDomainError,
    CoheriqEngineError,
    CoheriqEngineNotFoundError,
    CoheriqTypeError,
    CoheriqUserError,
    enable_engine,
    resolve_impl,
)


def f():
    return 42


def g(n=42):
    return 2 * n


def h(a=0, b=1):
    return 2 * a + b


class DefaultWidget:
    """A class candidate's default implementation."""

    backend = "default"


class EngineWidget:
    """An engine's override for the ``DefaultWidget`` candidate."""

    backend = "engine"


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


class TestResolveImpl:
    def test_default_returns_the_class(self):
        domain = AccelerationDomain("foo")
        widget = domain.acceleration_candidate(DefaultWidget)
        domain.materialize()
        assert resolve_impl(widget) is DefaultWidget

    def test_default_enables_isinstance(self):
        domain = AccelerationDomain("foo")
        widget = domain.acceleration_candidate(DefaultWidget)
        domain.materialize()
        instance = widget()
        assert isinstance(instance, resolve_impl(widget))

    def test_default_enables_new(self):
        domain = AccelerationDomain("foo")
        widget = domain.acceleration_candidate(DefaultWidget)
        domain.materialize()
        resolved = resolve_impl(widget)
        instance = resolved.__new__(resolved)
        assert isinstance(instance, DefaultWidget)

    def test_reflects_active_engine(self):
        domain = AccelerationDomain("foo")
        widget = domain.acceleration_candidate(DefaultWidget)
        domain.materialize()
        engine = AccelerationEngine("foo", "bar")
        engine.override(name="DefaultWidget")(EngineWidget)
        engine.materialize()
        enable_engine(domain, "bar")
        assert resolve_impl(widget) is EngineWidget
        assert isinstance(widget(), EngineWidget)

    def test_freezes_implementation(self):
        # Resolving is what calling a candidate would do: it locks in the
        # implementation, so an engine can no longer be enabled afterwards.
        domain = AccelerationDomain("foo")
        widget = domain.acceleration_candidate(DefaultWidget)
        domain.materialize()
        engine = AccelerationEngine("foo", "bar")
        engine.override(name="DefaultWidget")(EngineWidget)
        engine.materialize()
        resolve_impl(widget)
        with pytest.raises(CoheriqDomainError):
            enable_engine(domain, "bar")

    def test_wrapped_reaches_original_class(self):
        # __wrapped__ is the default-ignoring escape hatch; it stays the original
        # class even when an engine is active.
        domain = AccelerationDomain("foo")
        widget = domain.acceleration_candidate(DefaultWidget)
        domain.materialize()
        engine = AccelerationEngine("foo", "bar")
        engine.override(name="DefaultWidget")(EngineWidget)
        engine.materialize()
        enable_engine(domain, "bar")
        assert widget.__wrapped__ is DefaultWidget
        assert resolve_impl(widget) is EngineWidget

    def test_rejects_non_candidate(self):
        with pytest.raises(CoheriqTypeError):
            resolve_impl(int)

    def test_error_is_both_user_error_and_type_error(self):
        with pytest.raises(CoheriqUserError):
            resolve_impl(int)
        with pytest.raises(TypeError):
            resolve_impl(int)

    def test_function_candidate_returns_the_default_function(self):
        # A function candidate's wrapper forwards calls correctly, so what
        # resolve_impl adds is the implementation's identity: which object is
        # actually being called.
        domain = AccelerationDomain("foo")
        wrapped_f = domain.acceleration_candidate(f)
        domain.materialize()
        assert resolve_impl(wrapped_f) is f

    def test_function_candidate_reflects_active_engine(self):
        domain = AccelerationDomain("foo")
        wrapped_f = domain.acceleration_candidate(f)
        domain.materialize()
        engine = AccelerationEngine("foo", "bar")
        engine.override(name="f")(g)
        engine.materialize()
        enable_engine(domain, "bar")
        assert resolve_impl(wrapped_f) is g

    def test_function_candidate_identity_is_what_is_called(self):
        # The returned object is the one the wrapper dispatches to, so calling it
        # directly agrees with calling through the wrapper.
        domain = AccelerationDomain("foo")
        wrapped_f = domain.acceleration_candidate(f)
        domain.materialize()
        engine = AccelerationEngine("foo", "bar")
        engine.override(name="f")(g)
        engine.materialize()
        enable_engine(domain, "bar")
        impl = resolve_impl(wrapped_f)
        assert impl() == wrapped_f() == g()

    def test_function_candidate_freezes_implementation(self):
        domain = AccelerationDomain("foo")
        wrapped_f = domain.acceleration_candidate(f)
        domain.materialize()
        engine = AccelerationEngine("foo", "bar")
        engine.override(name="f")(g)
        engine.materialize()
        resolve_impl(wrapped_f)
        with pytest.raises(CoheriqDomainError):
            enable_engine(domain, "bar")


class TestEngineBasicInheritance:
    pass


class TestEngineDiamondInheritance:
    pass


# FIXME:
# - ensure that multiple domains don't interfere
