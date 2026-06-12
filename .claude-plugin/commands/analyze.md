---
description: Analyze repository for code hotspots and forensic signals
---

Run a forensic analysis of this repository using the bbu CLI:

1. Run: `bbu analyze-repo --output=json --days=90`
   - If the command fails with "gh" related warnings, re-run with `--no-ci`.
   - If `bbu` is not installed, tell the user: `uv pip install -e .` from the
     black-box-unlock repo, then retry.
2. Parse the JSON. Report, in order:
   - **Top 5 hotspots** by `hotspot_score` (commits x indentation complexity),
     with their `bugfix_commits` and `build_failures` counts.
   - **Coupled pairs**: files whose `coupled_with` ratio >= 0.5 - hidden
     dependencies; changing one without the other is a defect source.
   - **High-risk ownership**: files where `is_high_risk` is true.
   - **Flaky steps** from `flaky_steps`, if any.
3. Recommend: which 2-3 files deserve refactoring or extra review first, and why -
   ground every recommendation in the numbers you just reported.
