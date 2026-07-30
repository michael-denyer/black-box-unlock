---
description: Review the current change with calibrated repository evidence
---

Review the change that is about to ship:

1. Run `bbu review-change --base origin/main`.
   - If `origin/main` is not the intended upstream, use the base named by the
     user.
   - For index-only review, run `bbu review-change --staged`.
   - For unstaged and untracked work only, run `bbu review-change
     --working-tree`.
   - Use `--profile NAME` when `.bbu.toml` defines a profile for this review.
   - Use `--include-ci` only when failed GitHub workflow evidence is useful.
2. Report the returned `actions` in order. Preserve the exact paths, raw
   revision counts, observed coupling ratio, and confidence lower bound.
3. Treat an empty action list as a valid clean result. Do not invent extra
   recommendations or turn the evidence into a composite risk score.
4. Mention whether CI was disabled, available, partial, or unavailable. When an
   `inspect_ci_failures` action is present, link the returned run and say that
   its changed paths are implicated, not proven causal.

The command applies the selected profile, project path-role rules, support
floor, deterministic ordering, and three-action cap.
