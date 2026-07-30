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
