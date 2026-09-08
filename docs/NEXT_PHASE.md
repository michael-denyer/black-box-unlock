# Make repository companion checks useful

Help developers and coding agents remember specific repository obligations when the relevant files change.
Start with maintainer-confirmed checks and prove they beat the same instructions in `AGENTS.md`.
Use history and direct imports to suggest candidate checks only after that proof.
Deliver P1, then conditional P2, then conditional P3. Stop or narrow when a value gate fails.
This is a planning deliverable. No product implementation or scheduled execution has started.
The plan starts from main `97e57b8`, not the separate architectural refactor at `0bf9698`.

## How to read this

One box is one unit of work. Every box names the evidence that checks it. Check a box only when its evidence exists. The body is a how-to. The appendices explain the product contract, alternatives, and unresolved questions.

Execution uses `skills/poteto-mode/playbooks/autopilot-stack.md` from the installed plugin. P1, P2, and P3 are sequential. The user reviews and merges implementation PRs. Planning, implementation, and permission to merge are separate. A failed value gate can end this phase successfully with a documented stop decision.

Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

CLI and MCP evidence consists of saved input, output, timing, and exit status. These transcripts are more useful here than screenshots of JSON. The ten live lanes below are bounded scenarios, run in waves within the available worker limit. They do not require ten simultaneous agents. Skill names unavailable on this host use the Codex platform mapping and the repository's own commands.

## Program checklist

### Arm the program

- [ ] Obtain the user's instruction to implement this plan. Save that instruction with the standing orders. Do not start implementation merely because this planning document exists.
- [ ] Put this objective in the standing orders. "Execute docs/NEXT_PHASE.md in order P1, P2, P3. Require unit, live, and perf evidence. Stop at failed value gates. The user merges. Finish with either a verified useful pilot or a supported stop decision."
- [ ] Read the execution playbook, arena synthesis, and applicable leaf skills from the installed plugin. Record their paths in the run log.
- [ ] If the user requests unattended execution, use the platform's supported scheduler for a 30-minute audit and status message. Otherwise give progress during the active task. Do not create an automation as part of planning.
- [ ] On a stop instruction, halt workers and leave a pushed, inspectable state. Record the last verified SHA.

### Spawn owners

- [ ] Assign P1 first. Assign P2 only after P1's value gate passes. Assign P3 only after P2's usage gate passes. Record ownership and the parent SHA for each.
- [ ] Keep every writer in its own worktree. The coordinator owns branch topology and the final verdict. Use unprefixed branch names.
- [ ] Keep implementation within each PR's listed files. Review any expansion against that PR's user outcome before accepting it.

### PR mechanics, for every PR

- [ ] Use the repository's available forge CLI. Open each implementation PR against its verified parent and record the URL.
- [ ] Review the diff for unnecessary machinery and prose. Run `uv run prek run --all-files` and the relevant tests before the PR-facing push. Save both outputs.
- [ ] Triage review findings against the actual diff and behavior. Record fixes and rejected findings with evidence.
- [ ] Commit and push with hooks enabled. Pull with rebase, push, and verify an up-to-date, clean worktree. Remove only stashes created by this work and prune stale remote references.

### Verdict and merge, for every PR

- [ ] Have independent workers verify the exact head using the unit, live, and perf scenarios below. Save the base SHA, head SHA, commands, and verdict.
- [ ] Reverify affected behavior after a changed head. A planning score or worker summary is not a passing product check.
- [ ] Present the verified implementation to the user. Hold at merge-ready until the user merges or explicitly authorizes merging.

### Boot recipe, for every live lane

- [ ] Check out the specified immutable revision in an isolated worktree, install locked dependencies with `uv sync --all-extras --dev`, and record `bbu version`.
- [ ] Drive CLI behavior through the installed `bbu` command. Drive MCP through a real stdio client calling the registered tool. Direct Python function calls alone do not verify the MCP boundary.
- [ ] Save commands, stdout, stderr, exit status, and relevant Git state under `.audit/next-phase/<pr-id>/lane-<n>/`. Store evaluation outcomes separately from the repositories visible to reviewer agents.

## Prove that selected reminders beat repository instructions (P1)

**Depends on.** None.

**Files.**

- [ ] Create `scripts/pilot_companion_checks.py`, `tests/pilot/test_companion_checks.py`, and `docs/COMPANION_CHECK_EVALUATION.md`. Keep pilot fixtures under `tests/fixtures/companion_checks/`.

**Build.**

- [ ] Build a disposable, read-only prototype that matches exact trigger and companion paths against an explicit selected change. Render the contract in Appendix A. Do not add a production command or configuration format yet.
- [ ] Use BBU and one other user-maintained repository. Let the maintainer write up to six meaningful obligations using only information available before the trial. Record setup time. If only BBU is available, report an exploratory result and hold the broader rollout.
- [ ] Freeze the rules, task selection, reviewer model, time budget, and adjudication labels before the held-out trial. Use separate development examples for tuning.
- [ ] Define eligibility before inspecting outcomes or rule matches. Take the first ten human-authored, non-merge development changes touching tracked files in each repository after the rule freeze. Include changes that trigger no rule. Record exclusions and predetermined reasons. Retrospective cases need evidence that rules were known before the task; otherwise use them only for development.
- [ ] Compare those 20 changes in paired reviews. One fresh reviewer gets the rules in `AGENTS.md` and ordinary code/Git search. The other gets identical rules plus the selected reminders. Keep other instructions, repository access, and budgets equal. Randomize arm order and blind the adjudicator to the arm.
- [ ] Give both arms a repository containing only history reachable before the task and the selected task patch. Keep later fixes, outcome labels, and trial answers inaccessible. A current checkout with a hidden answer file or future Git refs is not an acceptable fixture.
- [ ] Label relevance, newly noticed valid obligations, false obligations, interpretation time, and duplicate reminders. Count zero-trigger changes and report results per repository. File inclusion alone never earns a successful-obligation label.
- [ ] Continue only when both repositories yield at least three meaningful rules within 15 minutes of setup each, at least 80% of emitted reminders are relevant, and the treatment finds valid obligations missed by the baseline on at least four of the 20 changes. Require more gains than reverse losses and zero false claims of coverage or correctness. Sparse or disputed results are inconclusive, not a pass.

**You see.**

- [ ] Publish one comparison table with case counts, paired gains and losses, setup time, false obligations, and the continue, narrow, or stop decision. Label the numerical gates as chosen pilot policy, not validated universal thresholds.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Run `uv run pytest tests/pilot/test_companion_checks.py`. Check literal expected matches and states for the fixture cases, including an unrelated changed test and a deleted companion.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes on the configured `swarm workers` model at the PR head, using the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Compare ordinary review and the new prototype on the same missing companion. Trunk lacks the prototype. Save `p1/lane-1/comparison.json`. Pass when both existing behavior and the added reminder are recorded honestly.
- [ ] Lane 2. Stage only a trigger. Save `p1/lane-2/output.json`. Pass when the matching obligation appears.
- [ ] Lane 3. Include the actual companion. Save `p1/lane-3/output.json`. Pass when its state is included without claiming the obligation is satisfied.
- [ ] Lane 4. Include an unrelated test. Save `p1/lane-4/output.json`. Pass when the missing companion remains visible.
- [ ] Lane 5. Match no rule. Save `p1/lane-5/output.json`. Pass when output says no matching rule, not clean review.
- [ ] Lane 6. Remove a configured companion. Save `p1/lane-6/output.json`. Pass when the missing target is explicit.
- [ ] Lane 7. Inspect both evaluation contexts. Save `p1/lane-7/context-audit.txt`. Pass when rule content is identical and future evidence is inaccessible.
- [ ] Lane 8. Inspect task selection. Save `p1/lane-8/cohort.json`. Pass when all consecutive eligible changes, including zero-trigger cases, are represented.
- [ ] Lane 9. Check blinded adjudication. Save `p1/lane-9/labels.json`. Pass when labels cite actual obligations and arm identities were withheld.
- [ ] Lane 10. Recalculate the value gate. Save `p1/lane-10/decision.json`. Pass when another worker reproduces the continue, narrow, inconclusive, or stop result from receipts.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Measure review time for both arms, added reminder-generation latency, and output bytes. Separate prototype work from reviewer time.
- [ ] Probe. Interleave both arms across the same cases. Measure reminder generation in 20 fresh processes with the frozen fixture and six rules.
- [ ] Baseline. Record ordinary-review task time and output before interpreting treatment results. Record hardware and dependency versions.
- [ ] Rule. Require reminder generation p95 below one second and median interpretation overhead no greater than one minute per matched change. These provisional budgets do not replace the value gate. Do not claim a speed ratio between a full review and reminder generation.

**Review gate.** None. P1 is not review-gated as a product interaction. It produces an experiment and an explicit product decision.

**Merge.**

- [ ] Obtain the root verdict at the recorded head and finish review triage. The user may merge the evaluator even when the product hypothesis fails. P2 remains blocked unless the value gate passes.

## Ship confirmed checks through one fresh operation (P2)

**Depends on.** P1's value gate passes.

**Files.**

- [ ] Edit `src/black_box_unlock/config.py`, `git/changes.py` only where selection correctness requires it, `cli.py`, `mcp_server.py`, `commands/review-change.md`, `hooks/hooks.json`, `README.md`, and `docs/CONFIGURATION.md`.
- [ ] Create `src/black_box_unlock/companion_checks.py` and its unit, CLI, and MCP contract tests. Reuse the proven pilot fixtures and remove duplicated pilot matching logic after migrating its callers.

**Build.**

- [ ] Implement the exact-path rule and result contract in Appendix A. Keep matching pure. Keep Git interpretation in `git/changes.py` and configuration validation in `config.py`.
- [ ] Add `bbu check-change` and MCP `check_change` as the focused confirmed-check operation. Require an explicit base, staged, or working-tree selection. Invoke neither full history analysis nor CI. Keep existing forensic tools available.
- [ ] Add strict `[[companion_checks]]` parsing to `.bbu.toml`. Reject duplicate IDs, empty instructions, and paths outside the repository. Do not execute rule text or configuration commands.
- [ ] Preserve selection-layer truth. Read companion existence from the selected snapshot, including the index for staged review. A source rename may match its old or new path; a copy does not inherit its source rule. A deleted companion is target-missing, not evidence of completion.
- [ ] Give every matching rule its own companion state. A summary may emphasize three attention items, but JSON retains all matched rules and text reports any hidden remainder. Never imply all obligations were considered when output is truncated.
- [ ] Make the plugin use explicit scope. Stop enabling the noisy per-edit guard by default; retain it as documented opt-in. Keep the new operation independent of cached aggregate forensics. Document the separate legacy cache limitation without making its repair a prerequisite.
- [ ] Document the boundary between confirmed checks and heuristic review. A project with no configured checks gets a useful no-rules result and setup guidance. It never falls back silently to speculative obligations.
- [ ] Run a one-week pilot after implementation. Record all invocations and weekly configuration upkeep. Proceed to P3 only if relevant use continues and upkeep remains below ten minutes per repository for the week. Do not schedule that observation until execution is authorized.

**You see.**

- [ ] Run `bbu check-change --staged` on the pilot repository. It names the applicable instruction, trigger, companion, companion state, and Git scope. An unrelated staged test changes none of those facts. Save the output.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Run the new companion-check tests plus `uv run pytest tests/unit/test_config.py tests/unit/test_cli.py tests/unit/test_mcp_server.py tests/integration/test_changes.py`. Verify invalid rules, per-rule state, selection snapshots, rename/copy behavior, and no implicit clean result.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes on the configured `swarm workers` model at the PR head, using the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Exercise staged-only work through both CLIs. Save `p2/lane-1/comparison.json`. Pass when legacy behavior is recorded and the new explicit command sees the staged trigger.
- [ ] Lane 2. Diverge index and disk companion contents. Save `p2/lane-2/snapshots.json`. Pass when staged review uses index existence and working-tree review uses its documented layer.
- [ ] Lane 3. Change trigger plus unrelated test. Save `p2/lane-3/output.json`. Pass when only a matching companion affects that rule's state.
- [ ] Lane 4. Stage the companion. Save `p2/lane-4/output.json`. Pass when state becomes included and the instruction remains an obligation to assess.
- [ ] Lane 5. Rename a trigger and copy another. Save `p2/lane-5/output.json`. Pass when rename provenance works and the copy gains no inherited rule.
- [ ] Lane 6. Delete a companion and use a stale rule target. Save `p2/lane-6/output.json`. Pass when both cases report target-missing rather than completion.
- [ ] Lane 7. Call the actual MCP server twice around a changed selection. Save `p2/lane-7/protocol.json`. Pass when results reflect the new selection without restarting the server.
- [ ] Lane 8. Run confirmed checks without history or network access. Save `p2/lane-8/isolation.json`. Pass when the configured check is returned without aggregate analysis or CI.
- [ ] Lane 9. Invoke without a selector, without rules, and with more than three matching rules. Save `p2/lane-9/statuses.json`. Pass when scope is required, no-rules is explicit, and nothing is silently omitted.
- [ ] Lane 10. Inspect installation and plugin behavior. Save `p2/lane-10/plugin.txt`. Pass when the guard is opt-in and the plugin selects the intended operation and scope without repeated edit warnings.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Measure check-command wall time and response bytes. Also measure the existing selected-change collector on trunk and head to detect selection regressions.
- [ ] Probe. Interleave 20 trunk and head collector runs on the same frozen repository and selection. Measure the new command in 20 fresh processes on that fixture.
- [ ] Baseline. Record trunk's selection time first. The new command has no trunk equivalent. Keep P1 prototype measurements as context, not a production speed claim.
- [ ] Rule. Require check-command p95 below one second with 100 rules and output below 32 KiB. Require selected-change collection p95 no more than 20% plus 100 ms above trunk. Do not claim a speedup by comparing full analysis with confirmed checks.

**Review gate.** The user reviews the CLI and MCP interaction before merge.

- [ ] Present the operator with the relevant transcripts, one terminal screenshot, and a short video showing staged work, an unrelated test, and the actual companion. Hold at merge-ready for the user's review.

**Merge.**

- [ ] Obtain the root verdict at the exact head, finish review triage, and hand off to the user to merge. Record pilot usage before starting P3.

## Help maintainers discover defensible companion rules (P3)

**Depends on.** P2's usage gate passes.

**Files.**

- [ ] Edit `src/black_box_unlock/git/log.py`, `git/coupling.py` only for evidence projection, `cli.py`, and the companion-check documentation. Add `src/black_box_unlock/companion_suggestions.py` and focused tests.

**Build.**

- [ ] Add read-only `bbu suggest-checks --file PATH`. Return at most three candidate companions, each with evidence and a copyable configuration draft. Do not write configuration or invent the maintainer's instruction.
- [ ] Start with existing file-level evidence. For Python tests, compare a cheap direct-import lookup with supported history. Label direct imports and historical co-change separately. Other languages retain history-only suggestions with that limitation visible.
- [ ] Extend generic history with commit IDs and retrieve at most three supporting commit references per suggestion. Verify references against the selected history endpoint. Preserve unusual path handling and existing collection tests. Reuse X-Ray retrieval pieces only where this avoids duplicate Git semantics.
- [ ] Orient historical evidence to the trigger. Report shared revisions divided by trigger revisions, both raw file counts, the symmetric relationship measure under its own label, window, and truncation. Never label any of these a defect probability.
- [ ] Require the maintainer to supply an instruction and confirm a candidate before it becomes a rule. An import or co-change is a suggestion, never an obligation. Missing history, unsupported syntax, and failed collection are distinct outcomes.
- [ ] Compare discovery with ordinary import search and `git log -- PATH`. Stop expanding discovery if it supplies no additional accepted useful rule or costs more setup time than manual rule entry. The confirmed-check operation can remain useful even if discovery fails.

**You see.**

- [ ] A maintainer can inspect the evidence for a candidate, reject it, or add a concrete instruction. The next explicitly scoped check uses only the confirmed configuration. Save the before-and-after session.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Run the new suggestion tests plus `uv run pytest tests/unit/git/test_log.py tests/unit/test_temporal_coupling.py tests/unit/test_cli.py`. Verify oriented counts, cited commits, bounds, sparse history, and exact separation between suggested and configured checks.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes on the configured `swarm workers` model at the PR head, using the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Run existing coupling and new discovery on an asymmetric pair. Save `p3/lane-1/comparison.json`. Pass when old metrics remain identifiable and new trigger-oriented evidence uses the correct denominator.
- [ ] Lane 2. Use a sparse source with two broad commits. Save `p3/lane-2/suggestions.json`. Pass when weak historical evidence does not become an obligation.
- [ ] Lane 3. Use a directly importing test. Save `p3/lane-3/suggestions.json`. Pass when the import reason is inspectable and does not claim coverage.
- [ ] Lane 4. Remove historical support. Save `p3/lane-4/status.json`. Pass when absent history is distinct from an unsupported test relationship.
- [ ] Lane 5. Use a non-Python source. Save `p3/lane-5/status.json`. Pass when history-only limitations are explicit without a fabricated structural link.
- [ ] Lane 6. Inspect every returned commit. Save `p3/lane-6/citations.txt`. Pass when each commit predates the evaluation endpoint and contains the cited path relationship.
- [ ] Lane 7. Include a bulk changeset and unusual paths. Save `p3/lane-7/evidence.json`. Pass when bulk exclusions and exact paths survive CLI serialization.
- [ ] Lane 8. Generate more than three candidates. Save `p3/lane-8/bounds.json`. Pass when output is capped with a visible remainder and deterministic order.
- [ ] Lane 9. Reject a suggestion, then explicitly configure one. Save `p3/lane-9/session.txt`. Pass when rejected suggestions never affect checks and only confirmed configuration does.
- [ ] Lane 10. Audit accepted rules against the ordinary-search baseline. Save `p3/lane-10/value.json`. Pass when the continue or stop decision follows recorded added value and setup cost.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Measure suggestion-generation latency, returned bytes, Git subprocess count, and maintainer setup time. Compare ordinary search on the same repository and path.
- [ ] Probe. Interleave 20 ordinary-search and discovery runs on frozen small and larger pilot repositories. Bound the history endpoint and candidate evidence before running.
- [ ] Baseline. Record direct-import search plus path-scoped Git lookup time first. Record repository sizes and hardware so the budget has a defined workload.
- [ ] Rule. Require discovery p95 below five seconds and output below 16 KiB on those workloads. A timeout returns partial or unavailable evidence, never no relationship. Require added accepted rules or lower setup time to justify keeping discovery.

**Review gate.** The user reviews candidate discovery before merge.

- [ ] Show the operator transcripts, a terminal screenshot, and a short video of suggestion, rejection, and explicit confirmation. Hold at merge-ready until reviewed.

**Merge.**

- [ ] Obtain the root verdict, finish review triage, and hand off for the user's merge. If discovery fails its value gate, document the narrower confirmed-check product and leave discovery unpromoted.

## Close the program

- [ ] Check every executed box against its evidence. Mark conditional work skipped with the gate decision that prevented it, rather than claiming it completed.
- [ ] Report shipped behavior, measured usefulness, false obligations, setup cost, limitations, and the next decision. Preserve reproducible receipts and pushed commits.

## Appendix A. Prototype evidence and product contract

The planning review reproduced four existing behaviors on main `97e57b8`. Aggregate MCP results remain stale after a commit. The per-edit guard repeats even after companions are edited. Default heuristic review omits staged-only work. An unrelated changed test suppresses generic test advice. These are implementation observations, not measured product harm.

An additional 365-day probe found that `review.py`'s first three historical test companions were broad two-of-two co-changes. Direct imports found `tests/unit/test_review.py` and `tests/integration/test_changes.py`. `git/changes.py` had no supported test companion. This supports including a cheap structural baseline; it does not prove test recommendation utility.

No proposed product experiment has run. P1 is the prototype gate. Rule adoption, net useful reminders, and upkeep remain unproven.

The proposed confirmed rule has exactly four fields.

```toml
[[companion_checks]]
id = "parser-round-trip"
trigger = "src/parser.py"
companion = "tests/test_parser.py"
instruction = "Check that format changes retain round-trip coverage."
```

This is illustrative proposed configuration, not accepted syntax in the current release. Paths are repository-relative exact matches. There are no globs, commands, conditions, or automatically generated instructions in P2.

The intended interaction is equally narrow.

```text
bbu check-change --staged

Check parser-round-trip
Check that format changes retain round-trip coverage.
Trigger: src/parser.py
Companion: tests/test_parser.py
State: needs-attention
Scope: staged changes only
```

Every result includes the rule ID and instruction, trigger and companion, selected Git scope and provenance, and one companion state. `included` means the path is in the selected change, not that the behavior is verified. `needs-attention` means the trigger matched and the companion is absent from the change. `target-missing` means the configured companion is absent in the selected snapshot. No changes, no rules configured, and no matching rules remain distinct outcomes. BBU neither executes tests nor records a persistent acknowledgement.

## Appendix B. Alternatives rejected

The [arena synthesis](NEXT_PHASE_ARENA.md) records all four proposals and the independent judge. Confirmed checks won as the smallest honest workflow. The first comparison must use the same rules in `AGENTS.md`, because a tool that merely reformats those instructions has not earned its maintenance cost.

Historical fix retrieval stays deferred. It is useful raw material but needs a separate relevance demonstration. Pure historical test witnesses overlap existing coupling and fail on sparse history. A Python test runner adds collection, execution, side effects, and language support before proving recommendations. Inspection-card completion adds state without proving useful inspection.

Keep the existing offline report, forensic APIs, and X-Ray available. Pause their feature expansion during this phase. Defer new scoring models, dashboards, semantic code analysis, cross-language adapters, automatic test execution, generated tests, and automatic rule creation.

## Appendix C. Risks

P1 can reveal that users prefer plain repository instructions. That is a valid stop. A small two-repository pilot is directional evidence and must not become a broad accuracy claim.

P2 can create rule maintenance work, stale targets, or false assurance. Exact paths, explicit target state, measured upkeep, and no completion claims address only part of that risk. Rule text remains repository-supplied instruction data, not authority to run arbitrary commands.

Legacy aggregate MCP caching remains a known limitation outside this phase. Record it in the product backlog. The new confirmed-check operation must never depend on it. Repair and performance validation for legacy queries belong in a separate change.

P3 can rediscover obvious relationships or rank accidental co-change. Compare direct imports and ordinary Git search, expose denominators, bound collection, and retain maintainer confirmation. Non-Python structural discovery is outside this phase.

The planning branch does not include the older architectural deepening branch. Reuse individual fixes only after checking them against current main and the new contract. Do not merge that branch as an assumed prerequisite.

## Appendix D. Links and reading list

Read [change review](CHANGE_REVIEW_DESIGN.md), [configuration](CONFIGURATION.md), [X-Ray](XRAY.md), [validation limits](VALIDATION.md), and [the current visual report](VISUAL_REPORT_V2.md) before changing their boundaries.

Read the installed `how` and `architect` skills before designing P2's public contract. Use `interrogate` if that contract remains contested. Use `show-me-your-work` for the execution decision trail and `unslop` for user-facing text. Experience First chose a recurring decision. Laziness Protocol kept rules exact and execution out of scope. Sequence Work into Verifiable Units put evidence before product expansion.

The external comparison is ordinary repository instructions and Git search. CodeScene's [documented MCP capabilities](https://helpcenter.codescene.com/articles/7208397-what-can-codescene-single-user-mcp-do) provide context for deferring a broad code-health or test-execution product, not evidence that this proposal works.
