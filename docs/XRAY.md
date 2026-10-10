# Function X-Ray

Per-function churn for one file — Tornhill's X-Ray. File-level hotspots tell you *which
file* is unstable; X-Ray tells you *which functions inside it* drive that instability.

## What it computes

For each function in the file: `revisions` (distinct commits touching it in the window),
lines added/deleted, `complexity` (the same indentation proxy bbu uses for files,
measured over the function's current span), and
`hotspot_score = revisions × complexity` — the file formula at function scale.
Functions are ranked by score; functions that no longer exist in the current snapshot
are excluded, matching file-level behavior (a commit that deletes a function still
credits its deletions to that function, not to a neighbour, but the row is then dropped
from the output).

When complexity cannot be measured (the current snapshot is too deeply nested for `ast`
to parse), `complexity` and `hotspot_score` are `null` and `score_unavailable_reason`
says why. A `null` score is unknown, not zero; for ordering only, such rows rank as if the score were 0.

## How

One `git log -p -U0` pass over the file's history, with git's built-in language diff
drivers injected via a temporary `core.attributesFile` (an in-repo `.gitattributes`
still wins) so hunk headers carry real function context.

- **Python**: each revision's content is fetched (`git show`, newest-first, capped at
  200 revisions like CodeScene) and hunks are attributed per line to exact `ast` spans —
  decorator-aware, with `Class.method` qualified names. Added lines map through the
  commit's own snapshot and deleted lines through its parent's snapshot, so removed
  code lands on the function that held it. Revisions that don't parse
  (e.g. Python 2 history) fall back to indentation-based boundary detection.
  A snapshot that hits the interpreter recursion limit is treated as unparseable, and
  the lines on that side of the diff (added lines for the commit's snapshot, deleted
  lines for the parent's) fall back to header-name attribution. When the current
  snapshot is unparseable, every tallied name is listed, including functions that no
  longer exist, because there is no current span list to filter against.
- **Other languages** (~27 covered by git's drivers): attribution uses the hunk-header
  function name. Boundaries and complexity are unknown there, so those functions rank
  by revisions with `complexity: 0.0`.
- **Unsupported languages** (any extension without a git diff driver, such as `.js` or
  `.ts`): X-Ray does not guess. `bbu xray` returns no functions and
  `"skipped": "unsupported language"`; the top-hotspot pass in `analyze-repo` sets
  `xray_skipped` on that file and does not count it in `xrayed_files`.

## Usage

```bash
bbu xray src/black_box_unlock/git/coupling.py --days 365   # one file, JSON to stdout
bbu analyze-repo --xray-top 5                              # auto X-Ray top 5 hotspots
```

MCP: the `xray_file` tool returns the same JSON; agents typically call `get_hotspots`
first, then X-Ray the top files.

Real output (this repo, 365-day window):

```json
{
  "path": "src/black_box_unlock/git/coupling.py",
  "revisions_analyzed": 4,
  "functions": [
    {
      "name": "detect_temporal_coupling",
      "start_line": 10,
      "end_line": 46,
      "revisions": 4,
      "lines_added": 47,
      "lines_deleted": 10,
      "complexity": 51.0,
      "hotspot_score": 204.0
    }
  ]
}
```

## Function coupling

The `coupling` list reports same-file function pairs that change together —
X-Ray's internal temporal coupling. Formula matches the file level:
`coupling_ratio = shared_revisions / min(revisions_a, revisions_b)`. To keep
small windows from producing noise, a pair is reported only when it shares at
least 2 commits **and** meets the ratio threshold (`--min-coupling`, default
0.3). Edit one half of a strong pair, check the other.

The exact pairs depend on the selected history window and current source
layout; use `bbu xray <path>` to inspect the current evidence rather than
relying on a stored example.

## Performance

Measured on this repository (230 commits in the 365-day window, `--no-ci`, five
alternating runs after a warm-up, wall time including `uv run` start-up):

```bash
uv run bbu analyze-repo --repo . --days 365 --no-ci --xray-top 0   # 0.32-0.33 s
uv run bbu analyze-repo --repo . --days 365 --no-ci --xray-top 5   # 1.88-2.14 s
```

The top-5 pass adds about 1.6 s here, roughly six times the base run. The cost is the
Python path: each analyzed revision costs one `git show` for its snapshot and, when the
commit removes lines, one more for its parent, bounded by the 200-revision cap per file.
Cost grows with the revision count of the hottest files, so use `--xray-top 0` on large
histories where analysis time matters. A single interactive `xray_file` call is
one file, one pass of this work.

## Limitations

- **Renames split identity** (file- and function-level). bbu analyzes with
  `--no-renames`, and the recency window ages renames out — same stance as file-level
  analysis.
- **Non-Python attribution is heuristic**: git's hunk-header context can attribute
  decorator/signature edits to the *preceding* function and cannot see nesting. Python
  avoids this via ast; other languages carry the error tail (and `complexity: 0.0`
  marks those rows as less authoritative).
- **Hunk headers truncate at ~80 bytes** — long signatures are matched by prefix.
- **Coupling is same-file only** — cross-file function coupling (CodeScene tier) would
  need repo-wide attribution; out of scope for now.
