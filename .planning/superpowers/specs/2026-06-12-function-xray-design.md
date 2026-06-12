# Function-Level Forensics — Tornhill X-Ray (BBU-6351)

## Goal

Per-function churn and hotspot scoring — Tornhill's X-Ray — so agents and humans can see
*which functions inside a hot file* drive its churn. The largest analytical upgrade
available to bbu, and the one CodeScene paywalls.

## Decisions (settled in brainstorm, 2026-06-12)

1. **Scope: hybrid.** `analyze-repo` auto-X-Rays the top N hotspot files (default 5,
   `--xray-top`, 0 disables) AND any file can be X-Rayed on demand.
2. **Engine: hunk headers + ast correction (option A).** Git hunk-header function names
   (with injected diff drivers) as the universal base for ~27 languages; for `.py`,
   per-revision `ast` spans correct the attribution exactly.
3. **Surfaces: CLI + MCP.** `bbu xray FILE` and a seventh MCP tool `xray_file`, both
   thin wrappers over one engine.

## Research grounding (workflow run, measured)

- Faithful-minimal X-Ray = per-function revision count × per-function complexity,
  targeted at one file, windowed. Not present in code-maat — fresh implementation.
- Per-file windowed `git log -p -U0`: 0.03 s on a 17k-commit repo (pytest clone);
  the auto top-5 adds negligible cost to analyze-repo.
- Injecting git's built-in diff drivers via a temp `core.attributesFile` dropped wrong
  class-line attributions on flask from 7465 to 745; `-U0` removes context-bleed
  entirely. In-repo `.gitattributes` still takes precedence (desired).
- Hunk headers truncate at ~80 bytes → function-name matching must be prefix-based.
- Headers structurally misattribute: decorator/signature edits go to the *preceding*
  function, nested defs shadow, whole-function deletions attribute to the previous
  function. The ast layer fixes all of these for Python and recovers `Class.method`
  qualified names.
- `ast.parse` raises SyntaxError on Python-2/broken historical revisions → indentation
  fallback (CodeScene's own "micro-grammar" approach).
- Rejected: `git log -L` (wrong extents, no pathspec, still must parse patches),
  universal-ctags (no PyPI wheel — breaks `uv tool install`), tree-sitter for now
  (packaging API churning; revisit behind a boundary-provider interface if demand).

## Design

### Data model (`core/models.py`)

```python
class FunctionChurn(BaseModel):
    name: str            # qualified: "ClassName.method", "outer.inner", or "func"
    start_line: int      # current-snapshot span, decorator-aware
    end_line: int
    revisions: int       # distinct commits touching the function in the window
    lines_added: int
    lines_deleted: int
    complexity: float    # indentation proxy over current span; 0.0 if unknown (non-Python)

    @computed_field
    @property
    def hotspot_score(self) -> float:
        return self.revisions * self.complexity


class FileXRay(BaseModel):
    path: str
    days: int
    revisions_analyzed: int
    revision_cap_hit: bool
    functions: list[FunctionChurn]   # sorted by (-hotspot_score, name)
```

- Python path: functions absent from the current snapshot are excluded (consistent with
  file-level behavior where deleted files drop out of the ranking). Header-only path
  (non-Python): no current-snapshot boundaries exist, so all header names are kept
  as-reported with `start_line=0, end_line=0, complexity=0.0`.
- `FileForensics` gains `functions: list[FunctionChurn] = []`, populated only for the
  top-N files in analyze-repo. JSON picks it up via pydantic automatically; HTML frozen.

### Engine (`git/xray.py`)

`xray_file(repo_path: Path, file_path: str, days: int = 365, rev_cap: int = 200) -> FileXRay`

1. One git pass:
   `git -c core.attributesFile=<tmpfile> log --since=<days>d --no-renames -p -U0
   --pretty=format:<commit marker> -- <file_path>`
   where the temp attributes file maps known extensions to git's built-in diff drivers
   (`*.py diff=python`, `*.go diff=golang`, ...). Added/deleted line counts come from
   the hunks themselves — no second numstat call.
2. Parse the patch stream → per commit: list of hunks
   `{old_start, old_count, new_start, new_count, header_funcname}`.
3. Python files: for each revision (newest first, stop at `rev_cap`),
   `git show <rev>:<path>` → ast spans (span starts at `decorator_list[0].lineno` when
   decorated; nested defs and methods get qualified names). Attribute each hunk to the
   span containing its post-image position (pure deletions: the span containing
   `new_start`). On SyntaxError → indentation-based def-boundary fallback. The hunk
   header name is ignored where ast succeeded.
4. Non-Python files: attribute by header funcname, prefix-matched.
5. Aggregate per function name across commits: distinct-commit count, summed line
   counts. Map names onto the *current* snapshot's functions; drop vanished names.
6. Complexity per surviving function from the current snapshot span — refactor
   `complexity.py` to expose a line-slice helper
   (`indentation_complexity_lines(lines: list[str]) -> float`) reused by both paths.

### analyze-repo integration (`analysis.py`, `cli.py`)

- `run_analysis(..., xray_top: int = 5)`: after sorting by hotspot score, X-Ray the top
  `xray_top` files that exist on disk; attach results to those `FileForensics.functions`.
- `AnalysisSummary` gains `xrayed_files: int`.
- CLI: `bbu analyze-repo --xray-top 5` (0 disables).

### On-demand surfaces

- CLI: `bbu xray FILE [--days 365] [--repo .] [--cap 200]` → `FileXRay` JSON to stdout.
- MCP (`mcp_server.py`): seventh tool `xray_file(path: str, days: int = 365)` → same
  JSON. Computed per call (no cache dependency), same lazy pattern as existing tools.

### Errors

- Path not tracked / no commits in window / file deleted from working tree → `FileXRay`
  with empty `functions` (not an error; the empty result is self-describing).
- git missing / not a repo → existing `GitToolNotFoundError` / `NotAGitRepoError`.
- ast failures fall back silently (debug log only).

### Testing (TDD)

- Unit: patch-stream parser (multi-hunk, deletion-only hunks, `-U0` shapes, truncated
  headers, binary files skipped); attributes-file content; ast span extraction
  (decorators, async def, methods, nested defs, qualified names); indentation fallback;
  attribution merge (post-image position, deletions); aggregation + deterministic sort.
- Integration: synthetic git repo fixture (tmp_path, scripted commits touching known
  functions) asserting exact revision counts per function; dogfood smoke on bbu itself.
- CLI/MCP: existing CliRunner/mock patterns.

### Docs

README (features table, MCP tool list), CLAUDE.md CLI block, CHANGELOG, `docs/XRAY.md`
(method, measured performance, limitations).

## Explicit punts (documented in docs/XRAY.md)

- **Rename tracking** (file- and function-level): headers can't see it; bbu already
  takes the code-maat stance at file level (`--no-renames`); the recency window ages
  renames out.
- **Function-level temporal coupling**: purely additive later once attribution exists;
  noisy within small windows.
- **tree-sitter multi-language exact boundaries**: revisit behind a boundary-provider
  interface when the packaging story stabilizes.

## Risks

- Residual misattribution for non-Python files (header error tail) — documented, and
  complexity 0.0 keeps those rows visibly less authoritative.
- Combined end-to-end error rate of headers+ast on real history is unmeasured —
  mitigated by the synthetic-repo integration tests and dogfooding.
- `git show` per revision (Python path) adds rev_cap-bounded subprocess calls — measured
  ms each; cap defaults to CodeScene's 200.
