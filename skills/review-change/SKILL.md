---
name: review-change
description: Review the current branch, index, or working tree with calibrated repository evidence from bbu. Use before opening a PR or when the user asks what to check in a change.
---

Review the change that is about to ship:

1. Run `bbu review-change --base origin/main`, or call the `review_change` MCP
   tool when the `black-box-unlock` server is connected.
   - If `origin/main` is not the intended upstream, use the base named by the
     user.
   - For index-only review, run `bbu review-change --staged`.
   - For unstaged and untracked work only, run `bbu review-change
     --working-tree`.
   - Use `--profile NAME` when `.bbu.toml` defines a profile for this review.
   - Use `--include-ci` only when failed GitHub workflow evidence is useful.
2. Report the returned `actions` in order. Preserve the exact paths, raw
   revision counts, directional coupling rate, and confidence lower bound.
3. Treat an empty action list as a valid clean result. Do not invent extra
   recommendations or turn the evidence into a composite risk score. If
   `omitted_actions` is non-zero, say how many candidates the cap dropped.
4. Mention whether CI was disabled, available, partial, or unavailable. When an
   `inspect_ci_failures` action is present, link the returned run and say that
   its changed paths are implicated, not proven causal.
5. Repeat any `warnings` the result carries, such as a shallow clone.

The command applies the selected profile, project path-role rules, support
floor, deterministic ordering, and three-action cap. History before a rename
counts toward the current path.
