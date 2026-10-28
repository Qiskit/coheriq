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


"""Proof of concept: one fresh interpreter per test, no os.fork().

Replaces pytest-forked's fork with a `python -m pytest <nodeid>` subprocess.
Reports are rebuilt from a JSON sidecar the child writes, so nothing
pytest-internal has to be pickled or marshalled across the boundary.
"""
import json, os, subprocess, sys, tempfile
import pytest


def pytest_addoption(parser):
    parser.addoption("--isolate", action="store_true",
                     help="run each test in a fresh interpreter (no fork needed)")


# ---- child side: dump outcomes to a sidecar file -------------------------
if os.environ.get("ISOLATE_CHILD_REPORT"):
    def pytest_runtest_logreport(report):
        path = os.environ["ISOLATE_CHILD_REPORT"]
        rec = {"when": report.when, "outcome": report.outcome,
               "longrepr": str(report.longrepr) if report.longrepr else None,
               "duration": getattr(report, "duration", 0.0)}
        with open(path, "a") as f:
            f.write(json.dumps(rec) + "\n")


_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
_SITECUSTOMIZE_DIR = os.path.join(_PLUGIN_DIR, "_covstart")


def _coverage_is_active():
    """True if the parent run is measuring coverage (pytest-cov or `coverage run`)."""
    try:
        import coverage
    except ImportError:
        return False
    return coverage.Coverage.current() is not None


# ---- parent side: spawn one interpreter per test -------------------------
@pytest.hookimpl(tryfirst=True)
def pytest_runtest_protocol(item, nextitem):
    if not item.config.getoption("--isolate") or os.environ.get("ISOLATE_CHILD_REPORT"):
        return None

    ihook = item.ihook
    ihook.pytest_runtest_logstart(nodeid=item.nodeid, location=item.location)

    with tempfile.TemporaryDirectory() as td:
        sidecar = os.path.join(td, "reports.jsonl")
        env = dict(os.environ, ISOLATE_CHILD_REPORT=sidecar)

        # A spawned child is a brand new interpreter: unlike a fork, it does not
        # inherit the parent's running Coverage object, so nothing measures it
        # and every line reports as uncovered.  coverage's documented fix for
        # subprocesses is COVERAGE_PROCESS_START plus a sitecustomize that calls
        # process_startup() -- which no-ops unless that variable is set, so this
        # is inert when running without coverage.
        #
        # Requires `parallel = true` (already set in pyproject.toml) so the
        # children write distinct .coverage.* files instead of truncating one
        # another, and a `coverage combine` before reporting.
        # The child must re-import this plugin by name, so its directory has to
        # be importable there.  Propagate it from __file__ rather than relying on
        # the caller's PYTHONPATH, so a tox env only needs `-p
        # pytest_isolate_spawn` and nothing about layout.
        pypath = [_PLUGIN_DIR]

        cov_rc = os.environ.get("COVERAGE_PROCESS_START")
        if cov_rc is None and _coverage_is_active():
            cov_rc = str(item.config.rootpath / "pyproject.toml")
        if cov_rc:
            env["COVERAGE_PROCESS_START"] = cov_rc
            pypath.append(_SITECUSTOMIZE_DIR)

        env["PYTHONPATH"] = os.pathsep.join(
            filter(None, [*pypath, env.get("PYTHONPATH", "")])
        )

        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
             "-p", "pytest_isolate_spawn", item.nodeid],
            env=env, capture_output=True, text=True,
            cwd=str(item.config.rootpath),
        )
        recs = []
        if os.path.exists(sidecar):
            with open(sidecar) as f:
                recs = [json.loads(l) for l in f if l.strip()]

    phases = {r["when"] for r in recs}
    if not recs or "call" not in phases:
        # child died before reporting: synthesize a crash report
        call = pytest.CallInfo.from_call(
            lambda: pytest.fail(
                f"isolated test process exited with {proc.returncode}\n"
                f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}",
                pytrace=False), "call")
        rep = ihook.pytest_runtest_makereport(item=item, call=call)
        ihook.pytest_runtest_logreport(report=rep)
    else:
        for rec in recs:
            rep = pytest.TestReport(
                nodeid=item.nodeid, location=item.location,
                keywords={}, outcome=rec["outcome"],
                longrepr=rec["longrepr"], when=rec["when"],
                duration=rec["duration"])
            ihook.pytest_runtest_logreport(report=rep)

    item.session._setupstate.teardown_exact(nextitem)
    ihook.pytest_runtest_logfinish(nodeid=item.nodeid, location=item.location)
    return True
