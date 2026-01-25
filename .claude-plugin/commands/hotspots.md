# Show Hotspots

Identify code hotspots - files that are both complex and frequently changed.

## Instructions

A hotspot is a file with:
1. **High churn**: Many commits in recent history
2. **High complexity**: Large file size or many functions (proxy for complexity)

These are the "crime scenes" - areas most likely to contain bugs or cause problems.

## Analysis Steps

1. Get file churn from git history (last 90 days)
2. Get file sizes as complexity proxy
3. Calculate hotspot score: `churn × log(file_size)`
4. Rank and display top hotspots

```bash
# File churn
git log --since="90 days ago" --pretty=format: --name-only | sort | uniq -c | sort -rn

# File sizes (for existing files)
find . -name "*.py" -o -name "*.ts" -o -name "*.js" | xargs wc -l 2>/dev/null | sort -rn
```

## Output Format

Present as a ranked list:
1. **filename** - X commits, Y lines (Score: Z)
   - Recent changes: brief summary
   - Risk factors: what makes this a hotspot
