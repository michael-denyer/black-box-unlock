---
description: Show file hotspots (high churn x complexity) for review prioritization
---

Identify the files most likely to harbor defects:

1. Run: `bbu analyze-repo --output=json --days=90 --no-ci`
2. From the JSON `files` array, take the top 10 by `hotspot_score`.
3. Present a table: path, commits, complexity, hotspot_score, bugfix_commits.
4. For the top 3, read the file and name the specific complexity driver
   (deep nesting, long functions, mixed responsibilities).
5. Suggest the single highest-leverage refactoring for each.

The score is Tornhill's hotspot formula: change frequency x complexity.
A high score means the team keeps modifying code that is hard to modify safely.
