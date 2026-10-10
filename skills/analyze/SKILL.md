---
name: analyze
description: Analyze the repository for code hotspots and forensic signals with bbu. Use when the user asks which parts of the codebase are unstable, risky, or worth refactoring first.
---

Run a forensic analysis of this repository using the bbu CLI:

1. Run: `bbu analyze-repo --output=json --days=90`
   - If the command fails with "gh" related warnings, re-run with `--no-ci`.
   - If `bbu` is not installed, tell the user: `uv tool install black-box-unlock`,
     then retry.
2. Parse the JSON. Report, in order:
   - **Top 5 hotspots** by `hotspot_score` (commits x indentation complexity),
     with their `bugfix_commits` and `build_failures` counts.
   - **Coupled pairs**: files whose `coupled_with` entries have
     `rate_to_partner` >= 0.5, hidden dependencies; changing one without the
     other is a defect source.
   - **High-risk ownership**: files where `is_high_risk` is true (more than
     three authors and no one holding half the commits).
   - **Flaky steps** from `flaky_steps`, if any.
3. Recommend which 2 or 3 files deserve refactoring or extra review first, and
   why. Ground every recommendation in the numbers you just reported.

If the `black-box-unlock` MCP server is connected, `get_hotspots`,
`get_coupled_files`, `get_ownership`, and `get_flaky_steps` return the same
evidence without parsing JSON. Every result carries `provenance` naming the
HEAD it read.
