# Typing assertions

These files are checked by `mypy`, not run by `pytest`.

`src/coheriq/py.typed` promises downstream type checkers that the decorators
preserve the signature of what they decorate. That promise lives entirely in
`TYPE_CHECKING`-only `@overload` blocks, so no runtime test can observe it --
only a type checker can. Without these files the overloads would be asserted
by a pull request description and nothing else.

`mypy test/` in `tox -e lint` is what runs them. The directory is named in
`addopts` as `--ignore`, following the convention already used by
`coverage_startup/` and `spawn_isolation/`, so pytest never collects it.

Two instruments appear here, and the difference matters:

- **Annotated assignment** (`f: Callable[[int], str] = ...`) checks signature
  compatibility structurally. This is what tests signature preservation.
- **`assert_type`** compares types *nominally*. It cannot be used against a
  `Callable[...]` literal, because mypy reports a decorated function as
  `def (xs: list[float]) -> list[float]`, which is not the same type as
  `Callable[[list[float]], list[float]]` even though the two are mutually
  assignable.

Negative cases are spelled as `# type: ignore[code]` and rely on mypy's
`warn_unused_ignores`: if a construct that should fail stops failing, the
ignore becomes unnecessary and mypy reports it. That is what keeps the
negative assertions honest.

Write them as decorator *applications*, not bare calls. A bare
`domain.acceleration_candidate()` matches the first overload with the TypeVar
left unsolved and is accepted; only applying the result forces mypy to choose
a factory overload and reject it.

`tox -e lint` runs pyright over this directory too, as a second opinion on the
same assertions. It agrees with mypy on every one of them, positive and
negative, which is the point: `py.typed` is a promise to every checker, so a
single checker confirming it proves less than it appears to.
