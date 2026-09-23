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

from unittest import mock

import pytest
from coheriq import (
    AccelerationDomain,
    AccelerationEngine,
    CoheriqDomainError,
    CoheriqEngineError,
    CoheriqEngineNotFoundError,
    activation,
    enable_engine,
)


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


class TestEngineBasicInheritance:
    pass


class TestEngineDiamondInheritance:
    pass


# FIXME:
# - ensure that multiple domains don't interfere
