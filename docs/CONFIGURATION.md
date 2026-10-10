# Project configuration

Black Box Unlock works without configuration. Add `.bbu.toml` at the repository
root when the built-in path roles or review defaults do not fit the project.

## Example

```toml
default_profile = "release"

[[path_roles]]
pattern = "app/**/*.vue"
role = "source"

[[path_roles]]
pattern = "tests/fixtures/**"
role = "generated"

[profiles.fast]
days = 30
max_actions = 1

[profiles.release]
days = 180
min_coupling = 0.4
min_shared_revisions = 3
include_ci = true
max_actions = 3
```

Run the default profile:

```bash
bbu review-change --base origin/main
```

Select a profile or override one value:

```bash
bbu review-change --profile fast
bbu review-change --profile release --days 90
```

The MCP `review_change` tool accepts the same `profile`, `days`,
`min_coupling`, `min_shared_revisions`, and `include_ci` values.

## Path roles

Each `[[path_roles]]` entry has a `pattern` and one role:

- `source`
- `test`
- `docs`
- `config`
- `migration`
- `generated`
- `other`

Project rules use first match wins and run before the built-in classifier. The
result records the matching pattern as `project:<pattern>`, so callers can
explain why a path received its role.

### Built-in rules

Built-in rules apply when no project rule matches. They run in this order.

- `test`: a `test`, `tests`, `spec`, `specs`, or `__tests__` directory at any
  depth. A basename that starts with `test_`, `test.`, or `spec_`. `conftest.py`.
  A basename ending in `_test`, `_tests`, `_spec`, `.test`, `.tests`, or `.spec`
  plus an extension (`foo_test.go`, `Foo.test.tsx`, `foo.spec.ts`,
  `foo_test.py`, `foo_spec.rb`, `foo_test.rs`). A class file ending in `Test` or
  `Tests` (`FooTest.java`, `FooTests.cs`) or in `Spec` (`FooSpec.scala`).
  A bare substring is not enough: `contest.py`, `latest.py`, and `protest/` are
  not tests.
- `docs`: a top-level `doc`, `docs`, or `documentation` directory, or a
  `.md`, `.mdx`, `.rst`, or `.adoc` file.
- `migration`: a `migration` or `migrations` directory at any depth.
- `generated`: a `generated`, `vendor`, or `node_modules` directory at any
  depth, a `.lock` or `.map` file, or a `.min.js` or `.min.css` file.
- `config`: a top-level `config`, `hooks`, `.githooks`, `.github`, or
  `.claude-plugin` directory, a `.toml`, `.yaml`, `.yml`, `.ini`, or `.cfg`
  file, or a `Dockerfile`, `Makefile`, or `package.json`.
- `source`: a known source extension.
- `other`: everything else.

The `docs` and `config` directory names match only the first path segment, so
`src/hooks/useThing.ts` and `src/docs/render.py` stay `source`. Use a project
rule for a nested directory that should differ.

Every file in the analysis output carries its role as `path_role`. The MCP
`get_hotspots` tool takes `roles`, a list of role names, and returns only files
with those roles. The filter runs before `top_n`. An unknown role name is a
tool error.

Patterns match repository-relative POSIX paths:

- `*` matches within one path segment.
- `**` crosses directory boundaries.
- `**/` matches zero or more directories.
- `?` matches one character within a segment.
- A pattern without `/`, such as `*.snap`, matches that basename anywhere.
- A pattern ending in `/` matches everything below that directory.

Absolute paths, parent traversal, backslashes, and character classes are
rejected. These restrictions keep matching consistent across operating systems.

## Review profiles

Every profile may set:

| Setting | Default | Constraint |
|---------|---------|------------|
| `days` | `90` | At least 1 |
| `min_coupling` | `0.3` | Between 0 and 1 |
| `min_shared_revisions` | `2` | At least 1 |
| `include_ci` | `false` | Boolean |
| `max_actions` | `3` | From 1 to 3 |

`default_profile` must name a profile in the same file. An explicit CLI or MCP
value overrides the selected profile. CI remains off unless a profile or caller
turns it on.

Unknown keys, invalid values, malformed TOML, and missing profile names stop the
review with a configuration error. `bbu doctor` reports the same failure under
`checks.config`.
