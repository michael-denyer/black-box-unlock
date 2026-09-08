# Next-phase arena decision

The user requested a next-phase plan and then asked to use poteto-mode arena to generate ideas. Four independent proposals were produced against the same task and current-main grounding. No product code was implemented. The final deliverable is the [conditional implementation plan](NEXT_PHASE.md).

## Compare the candidates

The rubric weighted additional user value at 30%, falsifiable evaluation at 25%, evidence honesty at 20%, a small implementable increment at 15%, and workflow and maintenance cost at 10%. Each criterion was graded from zero to four. These are design judgments, not measured product results.

| Candidate | Model | Proposed product | Coordinator / 100 | Cross-judge / 100 |
| --- | --- | --- | ---: | ---: |
| 1 | gpt-6-astra | Maintainer-confirmed companion checks | 77.5 | 90.0 |
| 2 | gpt-5.6-sol | Python test selection and execution | 66.9 | 81.25 |
| 3 | gpt-5.6-terra | Historical source-to-test witnesses | 67.5 | 72.5 |
| 4 | gpt-5.6-luna | Inspection cards with completion states | 41.3 | 43.75 |

The independent cross-judge ran on gpt-5.6-sol in a fresh context. The coordinator scored all candidates before reading its verdict. Both selected candidate 1. All four configured runners completed; three ran in the first wave and the fourth used the next available slot. There were no dropouts.

The judge valued candidate 2's concrete verification outcome more highly than the coordinator did. Both rejected its initial scope of AST attribution, pytest collection, configuration, execution, and result recording. The coordinator also discounted its claim that running tests would make no repository writes. Test execution can have side effects.

The initial judge table contained arithmetic errors in three weighted totals. Those totals were recalculated and the judge corrected them without changing criterion scores or the winning candidate. The corrected totals appear above.

## Select the smallest useful product

Candidate 1 separates an observed relationship from an actual repository obligation. A maintainer supplies the instruction; BBU recalls it when the matching path changes. The confirmed check does not need history analysis, a language parser, CI, a test runner, or a model call.

The premise may still fail. A rule in `AGENTS.md` may already do the job adequately. P1 therefore compares identical instructions with and without change-scoped reminders. This baseline was missing from the candidate's original pilot and is required in the final plan. The implementation is conditional on demonstrated additional value.

All four candidates rejected broad historical-fix retrieval as the first product commitment. Their shared concern was relevance. A prior fix touching the same file does not show why the current change needs it. The arena changed the coordinator's earlier recommendation from building richer retrieval first to testing confirmed obligations first. Retrieval remains available for a later experiment if actual usage demands it.

## Graft the useful parts

| Source | Accepted | Boundary retained |
| --- | --- | --- |
| Candidate 2 | A cheap direct-import lookup as a baseline and optional discovery signal; explicit accounting for setup and verification cost. | No AST-level change analysis, pytest collection, or execution in this phase. |
| Candidate 3 | A separate state for each source/companion relationship; an unrelated changed test cannot satisfy another relationship. | File membership is not coverage. Historical witnesses do not become obligations automatically. |
| Candidate 4 | A concise instruction, explicit outcome states, and selection provenance. | No card IDs, acknowledgement store, completion API, or claim that a recorded note proves inspection. |
| Coordinator review | Trigger-oriented co-change counts, a documentation baseline, no silent truncation, and selected-snapshot existence. | Keep facts, policy, and hypotheses separate. |

The final plan makes one coherent choice. Confirmed rules drive `check-change`. Later discovery suggests rules for a maintainer to assess. It does not combine three separate action systems.

## Reject expansion until value is visible

Keep the offline HTML report, X-Ray, and existing forensic tools available. Pause their feature expansion. Defer a general code-health product, semantic impact analysis, automatic test execution, generated tests, cross-language structural adapters, automatic rule creation, and a new cache framework.

The guard's repeated warnings are addressed by removing its default activation in P2. It remains opt-in. Legacy MCP caching stays a separate backlog item. The new operation is fresh and does not invoke that cache. Independent verification caught an earlier draft making legacy cache repair mandatory; that expansion was removed.

Exact-path rules can rot and require setup. P1 measures setup and comparison with documentation; P2 measures continued use and maintenance cost. P3 may be skipped even when confirmed checks work, if ordinary search supplies equally good candidates.

## Record what the evidence establishes

Main was inspected at `97e57b8c8ec8a0a6896341dd99a69ca496cc3e4a`. The original worktree remains on its earlier architecture branch. The planning worktree was created separately and no source files were changed.

The existing-behavior probes were rerun against current main during planning. They reproduced stale aggregate MCP results, repeated guard warnings, staged-only work omitted by the default heuristic review, and unrelated-test suppression. A separate history probe found broad two-of-two test companions for `review.py`, while direct imports identified its direct test files. These observations justify the baselines and acceptance cases. They do not prove prevention of defects or useful adoption.

Complete candidate proposals and rationales are retained in the session workspace under `/tmp/bbu-phase-arena/candidate-1/` through `candidate-4/`. The shared brief, source grounding, coordinator scores, corrected independent judgment, and process log are in the same workspace. They are working artifacts; this synthesis records the durable decision.

## Apply the principles to concrete choices

- Experience First chose one recurring review decision and made utility a gate before more features.
- Laziness Protocol kept rules exact, reused existing selection/configuration boundaries, and excluded execution and persistent acknowledgements.
- Separate Before Serializing Shared State gave each arena runner its own output directory and left final Git writes to the coordinator.
- Redesign From First Principles kept suggestions separate from confirmed obligations when combining candidate ideas.
- Sequence Work into Verifiable Units ordered the work as evaluation, confirmed checks, and conditional discovery.
- Prove It Works required live behavior receipts, corrected score arithmetic, and explicit labels for unrun product experiments.
- Guard the Context Window kept the source grounding compact and candidate documents outside the main conversation until comparison.

## Verification and attention

The plan checker passed the initial draft with three PR sections and zero problems. Independent review then found two substantive issues it cannot catch. The final plan excludes unrelated cache repair and defines eligibility independently of matching rules. Rerun the checker, Markdown validation, and reference checks on the final files. The delivery message records the final results.

The independent process-log review ran on gpt-5.6-sol. It found no measured-product overclaim. It noted that the dispatch brief is a derived record of the user's request, not independent authorization evidence. The actual user messages directly authorize planning and arena work. This distinction has no effect on the proposed product's unproven usefulness.

The unresolved attention item is product value. No proposed pilot has run. All rollout gates, latency budgets, and upkeep limits are chosen policies. Passing unit tests or this document's checker cannot satisfy them.
