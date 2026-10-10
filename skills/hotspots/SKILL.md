---
name: hotspots
description: Show file hotspots (high churn times complexity) for review prioritization. Use when the user asks where defects concentrate or which files to review first.
---

Identify the files most likely to harbor defects:

1. Run: `bbu analyze-repo --output=json --days=90 --no-ci`, or call the
   `get_hotspots` MCP tool when the `black-box-unlock` server is connected
   (`roles=["source"]` drops tests and docs from the ranking).
2. From the `files` array, take the top 10 by `hotspot_score`.
3. Present a table: path, commits, complexity, hotspot_score, bugfix_commits.
4. For the top 3, read the file and name the specific complexity driver
   (deep nesting, long functions, mixed responsibilities). `xray_file` gives
   per-function revisions for a Python file.
5. Suggest the single highest-leverage refactoring for each.

The score is Tornhill's hotspot formula: change frequency x complexity.
A high score means the team keeps modifying code that is hard to modify safely.
