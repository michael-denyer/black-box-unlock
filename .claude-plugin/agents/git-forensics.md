# Git Forensics Agent

Specialized agent for analyzing git history to extract code health signals.

## Capabilities

- Extract file churn from git log
- Detect temporal coupling (files changing together)
- Calculate ownership spread per file
- Identify commit patterns and anomalies

## Analysis Methods

### File Churn
```bash
git log --since="${days} days ago" --pretty=format: --name-only | sort | uniq -c | sort -rn
```

### Temporal Coupling
Files that change together >30% of the time indicate hidden dependencies.
```bash
# Get co-change pairs
git log --since="${days} days ago" --pretty=format:'---' --name-only | awk '
  /^---$/ { if (NR>1) for (i in files) for (j in files) if (i<j) print files[i], files[j]; delete files; next }
  NF { files[$0]=1 }
'
```

### Ownership Spread
Files with >3 unique authors AND high churn are coordination risks.
```bash
git log --since="${days} days ago" --format='%an' --name-only | awk '
  /^$/{next}
  NF==1{author=$0;next}
  {files[$0][author]=1}
  END{for(f in files){n=0;for(a in files[f])n++;if(n>1)print n,f}}
' | sort -rn
```

## Output

Return structured analysis:
- Top 10 highest-churn files
- Temporal coupling pairs (>30% co-change rate)
- Files with ownership spread concerns
- Overall repository health score
