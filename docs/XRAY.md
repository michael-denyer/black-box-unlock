# Function X-Ray

Per-function churn for one file — Tornhill's X-Ray. File-level hotspots tell you *which
file* is unstable; X-Ray tells you *which functions inside it* drive that instability.

## What it computes

For each function in the file: `revisions` (distinct commits touching it in the window),
lines added/deleted, `complexity` (the same indentation proxy bbu uses for files,
measured over the function's current span), and
`hotspot_score = revisions × complexity` — the file formula at function scale.
Functions are ranked by score; functions that no longer exist in the current snapshot
are excluded, matching file-level behavior.

## How

One `git log -p -U0` pass over the file's history, with git's built-in language diff
drivers injected via a temporary `core.attributesFile` (an in-repo `.gitattributes`
still wins) so hunk headers carry real function context.

- **Python**: each revision's content is fetched (`git show`, newest-first, capped at
  200 revisions like CodeScene) and hunks are attributed per line to exact `ast` spans —
  decorator-aware, with `Class.method` qualified names. Revisions that don't parse
  (e.g. Python 2 history) fall back to indentation-based boundary detection.
- **Other languages** (~27 covered by git's drivers): attribution uses the hunk-header
  function name. Boundaries and complexity are unknown there, so those functions rank
  by revisions with `complexity: 0.0`.

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

## Performance

Measured during design research: the windowed `-p` pass for one file took 0.03 s on a
17k-commit repository; the Python path adds one `git show` per analyzed revision
(milliseconds each, bounded by the 200-revision cap). Interactive MCP calls stay well
under a second; `--xray-top 5` adds negligible cost to `analyze-repo`.

## Limitations

- **Renames split identity** (file- and function-level). bbu analyzes with
  `--no-renames`, and the recency window ages renames out — same stance as file-level
  analysis.
- **Non-Python attribution is heuristic**: git's hunk-header context can attribute
  decorator/signature edits to the *preceding* function and cannot see nesting. Python
  avoids this via ast; other languages carry the error tail (and `complexity: 0.0`
  marks those rows as less authoritative).
- **Hunk headers truncate at ~80 bytes** — long signatures are matched by prefix.
- **No function-level temporal coupling yet** — a natural follow-up once per-function
  attribution exists; within small windows the percentages would be noisy.
