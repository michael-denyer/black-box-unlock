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
2. Report the returned `actions` in order. Preserve the exact paths, raw
   revision counts, observed coupling ratio, and confidence lower bound.
3. Treat an empty action list as a valid clean result. Do not invent extra
   recommendations or turn the evidence into a composite risk score.
4. Mention whether CI was disabled, available, partial, or unavailable.

The command already applies the support floor, path-role policy, deterministic
ordering, and three-action cap.
