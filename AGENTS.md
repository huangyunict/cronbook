# Python rules

## Style rules

- When creating Python files, use double quotes (`"`) instead of single quotes (`'`) for string literals.
- When writing Python files, debugging print statements should print to stderr (i.e., pass `file=sys.stderr` to `print()`).
- Python code should follow the "black" style (https://black.readthedocs.io/en/stable/index.html).
- When changing Python files, add Python type hint annotations.

## Formatting

Use Ruff (https://docs.astral.sh/ruff/formatter/) as the formatter. `ruff format` implements the
black style, so the style rule above still holds; only the tool differs.

For a new project, use Ruff only:

- Never add `black` as a dependency, and never add a `[tool.black]` section.
- Configure formatting under `[tool.ruff.format]` and linting under `[tool.ruff.lint]` in
  `pyproject.toml`.
- Format and lint with `ruff format` and `ruff check --fix`.

For an existing project, ask before switching:

- If the project already has `black` wired into CI (e.g. a `black --check` step), a pre-commit
  hook, or a `[tool.black]` section, ask the user whether to keep black or migrate to Ruff. Do not
  swap the formatter on your own.
- Never run both formatters over the same code. Ruff's output matches black's on nearly all code
  but not all of it (https://docs.astral.sh/ruff/formatter/black/), so two formatters will fight
  over the deviations.

## Type checking

Type hints are enforced, not advisory. Use `mypy` (https://mypy.readthedocs.io/) as the type
checker, and enable Ruff's `ANN` rules so missing annotations fail the lint.

For a new project, start strict:

```toml
[tool.ruff.lint]
select = ["ANN", "B", "DTZ", "E", "F", "I", "UP"]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["ANN"]

[tool.mypy]
strict = true
warn_unreachable = true

[[tool.mypy.overrides]]
module = "tests.*"
disallow_untyped_defs = false
```

For an existing untyped codebase, do not flip `strict` on globally - it produces thousands of
errors nobody reads. Ratchet instead: enable `strict` per module via `[[tool.mypy.overrides]]` and
append modules as they are cleaned up. Only append, never loosen an entry that already passes.

These commands are the gate, whether they run in CI or by hand:

```
uv run ruff check .
uv run ruff format --check .
uv run mypy src/
```

- Add a CI workflow running them only once the project has a remote that runs CI. Do not scaffold
  a workflow file into a project that has no remote yet - the commands above are the whole check,
  and a workflow that never runs is noise. Add it when the remote is added.
- A check that is not required by branch protection is advisory, so state that in the reply when
  the CI job is added but cannot be marked required.
- Pre-commit hooks (`ruff-pre-commit`, `mirrors-mypy`) are a convenience that catches errors
  earlier. They do not replace the CI gate: `--no-verify` bypasses them.
- Static checking stops at the process boundary. Validate data arriving from JSON, a database, the
  network, or the environment with `pydantic` at the boundary rather than trusting the annotation.

## Imports

Never use wildcard imports. Import every name explicitly, no matter how many come from the same
module.

- No `from foo.bar import *` - write out each name, e.g. `from foo.bar import Baz, Qux`.
- This includes re-exports in `__init__.py`: list the names and declare them in `__all__` instead
  of star-importing a submodule.
- `__all__` itself is still fine (and encouraged) as the declaration of a module's public API; the
  rule is about the import statement, not the export list.

Sort imports alphabetically: the names inside a single `from x import a, b, c`, and the statements
within each group (stdlib, third-party, first-party). This is what `isort`/`ruff --select I`
enforces, so let the tool do it.

```python
# Bad
from pathlib import *
from mypackage.models import *
from mypackage.models import User, Session

# Good
from pathlib import Path, PurePath
from mypackage.models import Session, User
```

## Time and Duration Types

Internal Python code represents a point in time as a timezone-aware `datetime.datetime` in UTC, and
an elapsed amount of time as a `datetime.timedelta`. Convert only at the boundary - the place where
an external interface dictates the type - and convert back as soon as data crosses inward.

`datetime` is both the aware and the naive type, so the annotation `datetime` proves nothing and
mypy cannot catch the mistake. That makes the rules below a runtime discipline, not a static one.

### Never construct or accept a naive datetime

- Get the current time with `datetime.now(timezone.utc)`. Never `datetime.now()` (naive local time)
  and never `datetime.utcnow()` (naive, despite the name, and deprecated since Python 3.12).
- Enable Ruff's `DTZ` rules (flake8-datetimez); they flag exactly these calls. They are in the
  `select` list in the type checking section above.
- Validate at the process boundary, where static checking stops: use `pydantic.AwareDatetime` for
  data arriving from JSON, a database, the network, or the environment. An annotation of `datetime`
  accepts a naive value silently, and the failure surfaces later as a `TypeError` on subtraction.
- Attach a zone with `zoneinfo.ZoneInfo` (stdlib since 3.9). Do not use `pytz` in new code: its
  zones must go through `localize()`, and passing one to `datetime(..., tzinfo=...)` yields a wrong
  historical offset instead of an error.

```python
# Bad
created_at = datetime.utcnow()
expires_at = datetime.now() + timedelta(hours=1)

# Good
created_at = datetime.now(timezone.utc)
expires_at = created_at + timedelta(hours=1)
```

### Pass durations as timedelta

- Fields, parameters, and return types are `timedelta`. Do not pass a duration as an `int` or
  `float`, and never name a parameter after a unit (`timeout_ms`, `ttl_seconds`) - the unit belongs
  to the type.
- Most stdlib and third-party APIs take bare float seconds (`time.sleep`, `socket.settimeout`,
  `asyncio.wait_for`, `subprocess.run(timeout=...)`, `requests(timeout=...)`), so this boundary is
  wide. Call `.total_seconds()` at the call site into that API, and keep every signature you own
  taking `timedelta`.
- `timedelta` has no months or years, correctly so. Do not fake a month with `timedelta(days=30)`;
  do calendar arithmetic on `date` with an explicit zone, or add `python-dateutil` and use
  `relativedelta` when the domain genuinely needs it.

```python
# Bad
def fetch(url: str, timeout_ms: int = 5000) -> bytes: ...


# Good
def fetch(url: str, timeout: timedelta = timedelta(seconds=5)) -> bytes:
    return httpx.get(url, timeout=timeout.total_seconds()).content
```

### Wall clock and monotonic clock are different clocks

- Measure elapsed time with `time.monotonic()`, or `time.perf_counter()` when resolution matters.
  Subtracting two wall-clock `datetime` values is wrong: NTP steps, manual clock changes, and DST
  transitions on a local zone all make that difference non-monotonic, and it can come out negative.
- Use an aware `datetime` only for a point in time that is meaningful outside the process - a
  record's `created_at`, an expiry sent to a client, a log timestamp.

### Injecting the clock

Take the current time from an injected callable so tests can fix it, rather than calling
`datetime.now` inside business logic:

```python
Clock = Callable[[], datetime]


def is_expired(
    expires_at: datetime, now: Clock = lambda: datetime.now(timezone.utc)
) -> bool:
    return now() >= expires_at
```

`time-machine` (or `freezegun`) is acceptable where injection would distort the design, but a
parameter is simpler and needs no dependency.

### Boundary conversions

Do each conversion in the adapter that owns that boundary (serializer, DTO, repository, client
wrapper), not scattered through business logic.

- JSON and other wire formats: serialize with `.isoformat()`, parse with
  `datetime.fromisoformat()` (handles a trailing `Z` and most ISO 8601 since Python 3.11). State the
  format explicitly with `strptime`/`strftime` when the peer does not speak ISO 8601. Do not rely on
  `str()`/`repr()` round-trips.
- Epoch numbers: `datetime.fromtimestamp(value, timezone.utc)` and `.timestamp()`. These carry no
  unit, so confirm seconds vs milliseconds at the boundary - a JavaScript peer sends milliseconds.
- SQL: store in a timezone-aware column (`timestamptz` on Postgres, SQLAlchemy
  `DateTime(timezone=True)`). A plain `timestamp` column silently drops the offset.
- Protobuf: `google.protobuf.Timestamp` and `Duration`, via `Timestamp.FromDatetime` /
  `ToDatetime(tzinfo=timezone.utc)` and `Duration.FromTimedelta` / `ToTimedelta`.
- Configuration, environment variables, and CLI arguments: parse to `timedelta` at the edge (e.g.
  `timedelta(seconds=int(os.environ["TIMEOUT_SECONDS"]))`), and let nothing downstream see the int.

### Civil calendar values

Use `date` for a genuine calendar date (a billing month, a user-facing day) and pair it with the
explicit `ZoneInfo` used to derive it. Note that `datetime` subclasses `date`,
so `isinstance(value, date)` is `True` for a `datetime` - test for `datetime` first, or check
`type(value) is date`, when the distinction matters.

## Unit tests

### Test framework

New projects use `pytest`, not the standard library's `unittest`. Plain functions and fixtures beat
`TestCase` subclasses: no boilerplate class per group of tests, composable fixtures instead of
`setUp`/`tearDown` inheritance, and parametrization built in.

- Write tests as module-level functions named `test_*`, in files named `test_*.py`. Do not subclass
  `unittest.TestCase`, and do not use `setUp`, `tearDown`, or the `assertXxx` methods that come with
  it.
- Share setup with fixtures in `conftest.py`, and cover input variations with
  `@pytest.mark.parametrize` rather than a loop inside one test or a copied test body.
- Use pytest's own helpers where they have no assertpy equivalent: `tmp_path`, `monkeypatch`,
  `capsys`, `pytest.approx` in a bare comparison, `pytest.mark.skipif`, `pytest.fixture`.
- `unittest.mock` stays fine - it is the mocking library, not the test framework. `pytest-mock`'s
  `mocker` fixture is an option, not a requirement.
- Run through the project environment: `uv run pytest`. Configure it under
  `[tool.pytest.ini_options]` in `pyproject.toml`; do not add `pytest.ini`, `tox.ini`, or
  `setup.cfg` for it.

For an existing project already built on `unittest`, match it rather than mixing two styles in one
suite, and say so in the reply. `pytest` runs `TestCase` tests, so it can still be the runner; a
conversion of the test suite is its own change, not a side effect.

### Assertions

Write assertions with `assertpy`'s fluent `assert_that`, not the built-in `assert` statement. A
chain reads left to right, keeps several checks on one subject together, and fails with a message
that names the actual and expected values without a hand-written message argument. `pytest`'s
assertion rewriting only introspects bare `assert` inside test modules it collects, so helpers in
a non-test module lose it silently; `assertpy` reports the same way everywhere.

- A new project always gets `assertpy`: `uv add --dev pytest assertpy` at scaffold time, with
  every test written against `assert_that` from the first one. There is no surrounding style to
  match yet, so the exception below never applies to a project being created.
- Use `assert_that(actual).is_equal_to(expected)` instead of `assert actual == expected`. Actual
  comes first, which is the order the sentence reads in.
- Map the rest the same way: `is_true()` / `is_false()`, `is_none()` / `is_not_none()`,
  `is_same_as()` / `is_not_same_as()`, `is_instance_of()`, `is_close_to(x, tolerance)` for floating
  point.
- Assert on raised exceptions with
  `assert_that(fn).raises(ValueError).when_called_with("x")`, which returns the error message for
  further chaining (`.contains("x")`, `.is_equal_to(...)`). Do not use `pytest.raises` for the
  assertion itself; keep it only where the context manager form is genuinely needed, such as
  inspecting the exception object's attributes.
- Use the typed asserts for collections, strings, and dicts (`contains`, `contains_only`,
  `does_not_contain`, `is_length`, `is_empty`, `starts_with`, `contains_key`, `contains_entry`)
  rather than asserting on `len(...)` or one element at a time.
- Prefer chaining several assertions on one subject over repeating the subject, and use
  `.described_as("...")` when the subject alone does not identify which case failed.
- Import each entry point explicitly, e.g. `from assertpy import assert_that`; the import rules
  above still apply.

```python
# Bad
assert len(names) == 2
assert names[0] == "bob"
assert "alice" in names
with pytest.raises(ValueError):
    parse("x")

# Good
assert_that(names).is_length(2).contains("bob", "alice")
assert_that(parse).raises(ValueError).when_called_with("x").contains("x")
```

Keep a bare `assert` only where `assertpy` has no equivalent (a complex predicate that would need a
custom matcher, or a narrowing assert that exists to satisfy mypy rather than to test anything), and
say so in the reply.

If `assertpy` is on the test class path, new tests use it even when neighboring tests in the same
file use bare `assert` or `unittest`'s `assertXxx`. Consistency with old tests is not a reason to
write a bare `assert`. Do not convert the existing tests as a side effect; a migration is its own
change.

In an existing project where `assertpy` is absent from the test class path, match the surrounding
tests rather than adding the dependency for a single test, and say so in the reply. On the class
path means it is declared in the project's test or dev dependencies (`[dependency-groups]`, a
`test` extra, or the equivalent in `requirements-dev.txt`), not merely importable from some ambient
environment. Adding it there is its own change, made when the user asks for it.

If mypy reports missing stubs for `assertpy`, silence that one module with a
`[[tool.mypy.overrides]]` entry setting `ignore_missing_imports = true`, rather than relaxing the
setting globally.

## Project management

Use `uv` (https://docs.astral.sh/uv/) to manage new Python projects. Do not use `pip`,
`virtualenv`, `pip-tools`, `poetry`, `pipenv`, or `conda` for new projects.

- Scaffold with `uv init --package my-project` (adds `pyproject.toml` and the `src` layout), then
  replace the generated `[build-system]` block per the build system rules below.
- Pin the interpreter with `uv python pin <version>`, which writes `.python-version`.
- Add and remove dependencies with `uv add` / `uv remove`; dev-only tools go in a dependency
  group, e.g. `uv add --dev pytest`. Do not hand-edit dependency lists in `pyproject.toml`.
- Commit `uv.lock`. Use `uv sync` to reproduce the environment and `uv lock --upgrade` to
  refresh pins deliberately.
- Run everything through the project environment: `uv run pytest`, `uv run my-project`. Do not
  activate the venv manually or call a global `python`/`pytest`.
- Run one-off tools without adding them as dependencies via `uvx <tool>` (e.g. `uvx ruff check`).

## New dependencies

Before adding a dependency that is not already in the project, look up its most recent **stable**
release and use that version. Never guess a version from memory or copy one out of a tutorial - the
training-data version is stale by definition.

- Let the tool resolve it: `uv add <package>` picks the latest compatible release and writes the
  constraint. Do not hand-write a version you have not verified.
- When a version must be stated explicitly, check it at the time of the change against PyPI
  (https://pypi.org/project/<package>/) or `uv pip index versions <package>`, and confirm the
  package is actively maintained rather than a look-alike or an abandoned name.
- Stable means a final release. Never pass `--prerelease=allow` or pin an `a`/`b`/`rc`/`.dev`
  version unless the user asks for it; PyPI's "latest" already excludes pre-releases.
- State the version chosen and where it was checked in the reply.
- Respect `requires-python`. If the latest stable drops support for the project's pinned
  interpreter, use the latest stable that supports it and say why in the reply.
- Do not upgrade unrelated existing dependencies as a side effect; `uv lock --upgrade` is a
  deliberate, separate change.

## Build system

Use `hatchling` (https://hatch.pypa.io/latest/config/build/) as the build backend for new projects:

```toml
[build-system]
requires = ["hatchling", "hatch-vcs"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/my_package"]
```

`hatch-vcs` is what derives the version from git tags; see the versioning rules below.

- `uv init` generates the `uv_build` backend, not hatchling. Overwrite that `[build-system]` block
  after scaffolding; `uv build`, `uv sync`, and `uv run` all work the same either way.
- Always set `packages` explicitly. Hatchling only auto-detects `src/<name>` when the import name
  matches the normalized distribution name, so the `my-project` / `my_package` split this file
  allows fails the build with no useful message.
- Hatchling ships every file under the listed package directory, so `py.typed` and other package
  data need no extra configuration. Verify once with
  `uv build && unzip -l dist/*.whl | grep py.typed`.
- Reach for hatchling's plugins when the project outgrows a plain wheel: `hatch-vcs` for a version
  derived from git tags, build hooks for generated files.
- Do not use `setuptools` for a new project. It stays the right choice only for C or Cython
  extension modules, and for existing projects already built on it - a backend swap on a working
  project is risk without payoff.

## License

Every new project gets a `LICENSE` file. Ask the user which license before creating it, and state
that the default is MIT; use MIT when the user has no preference or does not answer.

- Ask once, at scaffold time. Do not pick a license silently, and do not change the license of an
  existing project without an explicit request.
- If the project is internal or proprietary, the user says so in response to the question - write
  the license text they specify rather than substituting an open source one.
- Put the full license text in `LICENSE` at the repository root, with the correct copyright year
  and holder. Ask for the holder if it is not obvious from the git config or the repository.
- Declare it in `pyproject.toml` with a PEP 639 SPDX expression, not a classifier:

```toml
[project]
license = "MIT"
license-files = ["LICENSE"]
```

- `license-files` makes the backend ship the file inside the wheel under
  `dist-info/licenses/`; without it the metadata claims a license the artifact does not carry.
- Do not use the legacy `license = { text = "..." }` table or a
  `License :: OSI Approved :: ...` classifier in a new project. Both are deprecated by PEP 639.
- `uv init` does not create a `LICENSE` file, so this is always a manual step.

## Versioning

The version comes from the git tag, never from a literal in the source. A hand-maintained version
is a second source of truth that drifts from the tag it is supposed to match, and the mismatch is
only discovered after the artifact is already on PyPI.

Use `hatch-vcs`, and declare the version dynamic:

```toml
[project]
dynamic = ["version"]

[tool.hatch.version]
source = "vcs"

[tool.hatch.build.hooks.vcs]
version-file = "src/my_package/_version.py"
```

- Delete the `version = "0.1.0"` line that `uv init` writes. `version` in `[project]` and
  `version` in `dynamic` are mutually exclusive, and leaving both is a build error.
- Tag releases as `v1.2.3`. The leading `v` is stripped, so the tag `v1.2.3` builds
  `my_project-1.2.3`.
- The generated `_version.py` is a build artifact. Add it to `.gitignore` and never edit or commit
  it. Read the version at runtime with `importlib.metadata.version("my-project")` rather than
  importing the generated file, so it works for an installed package either way.
- CI must check out the full history and tags. `actions/checkout` defaults to a shallow clone,
  which hides the tags and silently produces a development version instead of failing:

```yaml
      - uses: actions/checkout@v5
        with:
          fetch-depth: 0
```

- A build with no reachable tag produces a local version such as `0.1.dev1+g6429071`. PyPI rejects
  any version carrying a `+local` segment, so a release that was tagged wrong fails at upload
  rather than publishing something incorrect. Treat that error as a missing or unfetched tag.
- Release by pushing the tag and publishing the GitHub release; do not commit a version bump.

## Publishing

Every new project is set up so it can be published to both TestPyPI and PyPI from the start, even
when there is no intention to release it yet. Retrofitting this later means fixing metadata after
a name is already taken or a bad version is already uploaded.

Configure both indexes in `pyproject.toml`, so publishing is `uv publish --index <name>` and no
upload URL is ever typed by hand:

```toml
[[tool.uv.index]]
name = "testpypi"
url = "https://test.pypi.org/simple/"
publish-url = "https://test.pypi.org/legacy/"
explicit = true

[[tool.uv.index]]
name = "pypi"
url = "https://pypi.org/simple/"
publish-url = "https://upload.pypi.org/legacy/"
explicit = true
```

- Mark both `explicit = true` so they are only used when named. Without it, TestPyPI can satisfy
  ordinary dependency resolution, which pulls in whatever placeholder someone uploaded under a
  matching name.
- The `url` is what `uv publish` checks to skip duplicate uploads; keep it set even though only
  `publish-url` performs the upload.

PyPI rejects incomplete metadata, so `[project]` needs more than `uv init` generates. Fill in
`description`, `readme`, `requires-python`, `authors`, `license`, `license-files`, and:

```toml
[project.urls]
Homepage = "https://github.com/<owner>/<repo>"
Repository = "https://github.com/<owner>/<repo>"
Issues = "https://github.com/<owner>/<repo>/issues"
```

Everything above is plain `pyproject.toml` metadata: it belongs in every new project, costs
nothing, and is what makes a later release possible without a metadata scramble.

The release workflow is separate, and is created only when the project has a GitHub remote. Trusted
publishing authenticates as the workflow's own identity, so it cannot work before a remote exists.
Add the workflow when the remote is added, not at `uv init` time. On GitLab or another host, use
that host's OIDC equivalent rather than the file below.

Authenticate with trusted publishing (OIDC), not API tokens. Register the repository as a trusted
publisher on PyPI and TestPyPI, then publish from CI:

```yaml
name: publish
on:
  release:
    types: [published]

jobs:
  publish:
    runs-on: ubuntu-latest
    environment: pypi
    permissions:
      id-token: write
    steps:
      - uses: actions/checkout@v5
        with:
          fetch-depth: 0        # tags must be present for the version
      - uses: astral-sh/setup-uv@v7
      - run: uv build
      - run: uv publish --trusted-publishing always
```

- `permissions: id-token: write` is what mints the OIDC token. Without it the job falls back to
  looking for credentials and fails.
- Never commit an API token, and do not add one to the repository secrets when trusted publishing
  is available. Use a token only for a local one-off upload, via `UV_PUBLISH_TOKEN`.
- Verify the release path against TestPyPI before the first real upload:
  `uv build && uv publish --index testpypi`. Add `--dry-run` to check the files without uploading.
- A version can never be re-uploaded or replaced on either index, and yanking does not free it.
  Bump the version instead of retrying a failed release.
- Check the distribution name is free on both indexes before settling on it. TestPyPI is a
  separate namespace with separate accounts, so a name being free on one says nothing about the
  other.

Pin the action versions above to whatever is current when the workflow is created rather than
copying them verbatim.

## Project layout

When creating a new Python project, use the `src` layout so the package is only importable after
installation, and tests run against the installed package rather than the working directory.

At init time, create only what is needed to run `main`. Do not scaffold placeholder packages or
empty directories (no `core/`, `_internal/`, `docs/`, `scripts/`); add them when there is real
code to put in them.

```
my-project/
  pyproject.toml            # build backend, deps, tool config (ruff, mypy, pytest)
  uv.lock                   # uv-managed lockfile; commit it
  README.md
  LICENSE                   # asked at scaffold time; MIT by default
  .gitignore
  .python-version           # interpreter pin written by `uv python pin`
  src/
    my_package/
      __init__.py
      py.typed              # marker so type hints are exported to consumers
      _version.py           # generated by hatch-vcs at build time; gitignored
      main.py               # CLI entry layer (argparse); writes to stdout/stderr
  tests/
    test_main.py
```

Generate `main.py` with this skeleton:

```python
import argparse
from typing import Any


def parse_args(argv: list[str] | None = None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(prog="my-project")
    return vars(parser.parse_args(argv))


def main(argv: list[str] | None = None) -> int:
    options = parse_args(argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Rules:

- Build the parser and parse in a separate `parse_args(argv)` function that returns a plain dict;
  keep `main` free of parser wiring. Use `argparse.ArgumentParser` and convert the namespace via
  `vars(...)`; do not construct a settings/config object with per-flag fields from the namespace.

- One distribution name (`my-project`) to one import package (`my_package`); underscores in the
  import name, hyphens in the distribution name.
- Keep all packaging and tool configuration in `pyproject.toml`. Do not add `setup.py` or
  `setup.cfg` to new projects.
- Name the CLI entry module `main.py`, not `cli.py`. Declare console entry points under
  `[project.scripts]` pointing at a function in `main.py`. Add `__main__.py` only if
  `python -m my_package` is actually wanted, and keep it a thin delegate to that function.
- Mirror the `src/my_package/` tree under `tests/`, growing it as modules appear. Tests are not a
  package: no `__init__.py` in `tests/` unless test module names collide. Add `conftest.py` only
  once there are shared fixtures.
- Always create an empty `py.typed` next to `__init__.py` in a new package, even when nothing
  imports it yet. Without the marker (PEP 561), type checkers ignore the package's annotations
  entirely and treat every import from it as `Any`. The file costs nothing, and an application
  that later becomes a library would otherwise ship hints that silently do not apply. For an
  existing package that has no marker, adding one asserts the annotations are correct, so type
  check it first.
- Keep the public API explicit in the top-level `__init__.py` via `__all__`; anything prefixed
  with `_` is not public.
- As the project grows, split library code into modules or subpackages under `src/my_package/`.
  Library code logs via `logging` and never prints; only `main.py` writes to stdout/stderr.

