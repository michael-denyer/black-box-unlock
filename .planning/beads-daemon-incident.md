# Beads daemon incident — diagnosis and runbook (2026-06-12)

**RESOLVED 2026-06-12 21:08** — bd upgraded to 0.49.0, daemon re-enabled (event-driven,
no pull loop), `beads.left.*` artifacts retired to /tmp/beads-debug, flush verified
end-to-end (create + tombstone delete both reached issues.jsonl). issues.jsonl is now a
full export (the upstream model) rather than delta lines — fresh clones hydrate
completely. Note for the future: if issues.jsonl is ever edited by hand, run
`bd sync --import-only` once, or the pre-export guard refuses to flush.

## Symptoms

1. `bd create/update/close` mutations never reached the git-tracked `.beads/issues.jsonl`
   (BBU-6352's close had to be hand-copied in; commit 457c032).
2. `.beads/daemon.log` showed an endless 5-second cycle: export → `git pull` → import.
3. `bd sync` / `bd sync --flush-only` / `bd export` reported "no changes" while the db
   held unexported mutations — and **consumed the pending-change flags in the process**
   (silent data loss from the flush queue).

## Root cause (verified at source level)

Two bd versions have been operating on the same `.beads` directory:

- `~/go/bin/bd` = **v0.17.7** (go install, built Oct 2025) — what this machine's PATH
  resolves today, and what ran the daemon.
- A **v0.49.0** bd (brew, since uninstalled — see `~/.zsh_history`: brew upgrades through
  Feb 2026) initialized the modern `.beads` layout on 2026-01-25: it wrote
  `metadata.json`, `interactions.jsonl`, the `beads.left.*` merge-snapshot artifacts
  (`beads.left.meta.json` says `{"version":"0.49.0","timestamp":"2026-01-25T12:21:36Z"}`),
  and stamped the db schema 0.49.0 (the "Database schema version mismatch" error at
  14:20:53 in daemon.log).

v0.17.7 resolves the JSONL path with a glob — `beads.go:145` (tag v0.17.7):

```go
pattern := filepath.Join(dbDir, "*.jsonl")
matches, _ := filepath.Glob(pattern)
if len(matches) > 0 { return matches[0] }   // glob output is sorted
```

`beads.left.jsonl` (and even `interactions.jsonl`) sort before `issues.jsonl`, so every
v0.17.7 write path — daemon cycle export/import, CLI auto-flush (`flushToJSONL`),
`bd sync` — read and wrote **`beads.left.jsonl`**, a gitignored file, then ran
`git status` on it and concluded "No changes to commit". issues.jsonl was only ever
written by the newer bd (or by hand). Upstream confirmations: beads issues #301 and
#709; mitigated v0.24.0, fully fixed v0.26.0 (`FindJSONLInDir` prefers issues.jsonl and
skips merge artifacts).

The 5-second loop is v0.17.7's **designed** daemon default (`--interval`, 5s), each tick
doing a full export and an unconditional `git pull`. Newer versions (≥0.23) are
event-driven; the January daemon.log lines from the 0.49 binary show
"using event-driven mode / Auto-pull disabled".

Empirical confirmations on this repo (2026-06-12 20:26–20:30):

- Created throwaway issues; `dirty_issues` row persisted ≥18s while the daemon logged
  "Exported to JSONL" every 5s; issues.jsonl mtime frozen. Daemon restart did NOT help.
- `bd sync --flush-only` cleared `dirty_issues` (1→0) with no file write — the
  reproducible data-loss step.
- v0.49.0 (built to /tmp/beads-test, tested against a full copy of this repo in
  /tmp/bbu-beads-test with the poisoned artifacts left in place) flushed a created issue
  into issues.jsonl **in the same second**, ignoring beads.left.jsonl.

## Current state (left intentionally)

- Daemon **stopped**; `auto-start-daemon: false` in `.beads/config.yaml` (TEMP — see
  comment there) so a stray `bd` command can't resurrect the broken 0.17.7 daemon.
- `beads.left.jsonl` **deliberately NOT deleted**: while v0.17.7 is on PATH it shields
  the tracked `interactions.jsonl` from becoming the glob target. Delete it only after
  the upgrade.
- db (59 issues) and git history agree: BBU-6352/6353 closed, throwaway test issues
  deleted. issues.jsonl carries the latest delta lines, consistent with db state.
- Evidence preserved in `/tmp/beads-debug/` (pre-fix daemon.log, jsonl snapshots);
  v0.17.7 source in `/tmp/beads-src`; test sandbox in `/tmp/bbu-beads-test`.

## Runbook: permanent fix

1. Upgrade the PATH binary (pinned; the db schema is already 0.49.0):

   ```bash
   go install github.com/steveyegge/beads/cmd/bd@v0.49.0   # or any 0.49.x
   bd version    # expect 0.49.0
   ```

   Do NOT jump to 1.0.5 — it is gated upstream (migration 0043 can break multi-machine
   sync; pin 1.0.4 or wait for 1.0.6 if you want the 1.x Dolt architecture, and take a
   `bd backup` first).

2. If bd complains about repository fingerprint after upgrade:
   `bd migrate --update-repo-id` (URL canonicalization changed across versions).

3. Re-enable the daemon: set `auto-start-daemon: true` (or delete the TEMP block) in
   `.beads/config.yaml`. The 0.49 daemon is event-driven — no 5s pull loop.

4. Clean the stale artifacts (safe only after the upgrade):

   ```bash
   rm .beads/beads.left.jsonl .beads/beads.left.meta.json
   ```

5. Verify end-to-end: `bd create "flush check" -p 4 -t chore`, confirm the issue appears
   in `.beads/issues.jsonl` within a few seconds, then `bd delete <id>` and commit.

6. Keep only one bd install. The version skew (brew vs go install) caused this: the
   newer brew bd built the modern .beads state, then its uninstall silently demoted the
   repo to the old go-installed binary.
