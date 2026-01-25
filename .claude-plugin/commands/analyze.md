# Analyze Repository

Analyze the current repository for code forensics insights.

## Instructions

Run git forensics analysis on the current repository to identify:
- **File churn**: Files with high commit frequency
- **Temporal coupling**: Files that change together
- **Hotspots**: High churn × complexity areas
- **Ownership spread**: Files with many contributors

Use the git-forensics agent to perform the analysis, then summarize findings.

## Default Analysis

```bash
# Get file churn (commits per file, last 90 days)
git log --since="90 days ago" --pretty=format: --name-only | sort | uniq -c | sort -rn | head -20

# Get recent contributors per file
git log --since="90 days ago" --format='%an' --name-only | awk '/^$/{next} NF==1{author=$0;next} {print $0, author}' | sort | uniq | cut -d' ' -f1 | sort | uniq -c | sort -rn | head -20
```

Present results in a table showing:
| File | Commits | Contributors | Risk Level |
