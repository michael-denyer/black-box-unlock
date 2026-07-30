# Change Review design

Black Box Unlock v1.3 adds one product promise:

> Review the change that is about to ship and return at most three checks backed
> by repository evidence.

The review is a fresh JSON query. It does not add an HTML surface, cache final
advice, or enable CI unless the caller asks for it.

## Caller contract

```bash
# Branch commits plus staged, unstaged, and untracked work from the merge base
bbu review-change --base origin/main

# Only the index compared with HEAD
bbu review-change --staged

# Only unstaged tracked files and untracked files
bbu review-change --working-tree
```

The MCP `review_change` tool returns the same result model. The plugin
`/review-change` command invokes that typed operation and reports its actions
without inventing additional ranking rules.

## Shape

```text
CLI / MCP / plugin
        |
        v
run_change_review(request)       fresh, CI off by default
        |
        +--> collect_change_set()
        |
        +--> run_analysis(ensure_paths=changed current paths)
        |
        v
project_change_review()          pure and deterministic
        |
        v
ChangeReviewResult               zero to three typed actions
```

`collect_change_set` owns Git interpretation. `run_analysis` remains the
authoritative history and forensics join. `project_change_review` is the only
place that turns facts into actions. CLI, MCP, Markdown commands, and hooks are
adapters, not policy owners.

## Change selection

The request uses a discriminated selector rather than overlapping booleans.

- `base` resolves the merge base of the requested ref and `HEAD`, then includes
  committed branch changes, staged changes, unstaged changes, and untracked
  files.
- `staged` compares the index with `HEAD` and includes no other layer.
- `working-tree` includes unstaged tracked changes and untracked files.

Git name-status output is NUL-delimited so whitespace, Unicode, tabs, and
newlines in paths remain valid. Renames retain both paths. An unresolved merge
conflict is a typed selection error rather than a misleading review.
Staged and working-tree review also work before the repository's first commit;
their provenance records `head_oid` as `null`.

## Evidence and ordering

Raw temporal-coupling pairs remain authoritative:

```text
coupling ratio = shared revisions / min(revisions A, revisions B)
```

Every review coupling includes the shared revision count, both file revision
counts, the observed ratio, and the 95% Wilson lower confidence bound. By
default, pairs with fewer than two shared revisions do not produce review or
hook actions.
Eligible pairs are ordered by:

1. Wilson lower bound, descending.
2. Shared revisions, descending.
3. Observed coupling ratio, descending.
4. Paths, ascending.

This makes repeated evidence outrank a perfect ratio from one observation
without replacing evidence with an opaque risk score.

Ordered path-role rules classify source, test, docs, config, generated, and
other paths. Project rules from `.bbu.toml` run first; fixed built-ins handle
the rest. The matched rule is returned with the role. Roles affect only
documented action policies and never change historical counts.

Named `.bbu.toml` profiles set the history window, coupling threshold, support
floor, CI choice, and action cap. CLI and MCP values override the selected
profile. The result records the profile name and config path with the effective
parameters.

## Actions

The result contains at most one action of each kind:

- `check_coupled_paths` when a supported historical companion is absent from
  the selected change.
- `add_or_update_tests` when source code changed but no test path changed.
- `inspect_ci_failures` when a selected path appears in a failed workflow run.
  Its evidence retains the workflow, run ID and URL, commit, timestamp, and
  matching paths. The action states that this is implication, not proof of
  causality.
- `focus_review` when changed code has defect history or diffuse ownership.

Each action embeds the typed evidence that caused it. Empty action lists are
valid. A separate `no_changes` result distinguishes no selected change from a
change for which no evidence met the action floor. Both variants report CI
status.
The supporting coupling list is capped at the strongest 20 relationships so a
large change cannot turn the primary result into an unbounded metrics dump.

## Freshness

Every review collects the change and history during the request. MCP review
bypasses the existing process cache, and the result records resolved object
IDs, included change layers, observation time, parameters, and
`cache_used=false`. CI is disabled by default.

The existing ambient coupling guard remains intentionally small. Its hook
adapter parses Claude hook JSON in Python, so the plugin no longer depends on
`jq`. The complete change review remains an explicit command instead of a slow
analysis after every edit.

## Added in v1.4

- Project path-role rules and named review profiles in `.bbu.toml`.
- Actionable failed-run evidence for opt-in CI review.
- Strict config parsing at the CLI and MCP boundary. Invalid configuration
  cannot reach review policy.

## Rejected for v1.3 and v1.4

- A composite change-risk score.
- A full change review on every edit.
- A new repository-facts cache or dirty-content fingerprint cache.
- Dashboards, HTML additions, PR-process telemetry, and wider language parsing.
- Complexity-growth advice without a validated threshold. Current complexity
  remains visible in file evidence; historical coupling and defect evidence
  drive the first bounded action contract.

## Verification contract

- Base, staged, and working-tree modes isolate exactly their documented layers.
- Untracked changed files appear with current complexity and zero history.
- A supported repeated coupling ranks ahead of a `1/1` pair.
- Raw counts survive core, CLI JSON, and MCP JSON.
- A covered companion never becomes a missing-companion action.
- No result can contain more than three actions.
- Repeated MCP review calls re-read current change state.
- The hook produces valid hook JSON or no stdout, never blocks an edit, and
  contains no `jq` dependency.
- Existing analysis and frozen HTML behavior remain compatible.

## Tournament rationale

Three independent designs were scored against interface depth, type safety,
Git semantics, calibrated evidence, freshness, hook noise, path roles, and
implementation risk. Candidate 1 was selected as the base. Candidate 2's pure
ranker boundary and Candidate 3's explicit no-change result were grafted into
it. Candidate 3's cache, configuration, session-state, and package-split
proposal was rejected as premature machinery for this release.
