---
name: resolve-pr-threads
description: Marks GitHub PR review threads as resolved via the GitHub GraphQL API. Accepts comment IDs from a file, stdin, or explicit IDs. Use after applying fixes to a PR branch.
---

# Resolve PR Threads

Resolves GitHub PR review threads: you supply a list of comment IDs (from a file, stdin, or as arguments), and the script maps them to threads and calls GitHub's resolve API.

**Prerequisite:** You need a list of comment IDs—either from the fetch-pr-comments step (file or stdout) or the IDs you applied fixes for. There is **no default input file**: you must pass `--input`, `--stdin`, or explicit IDs.

## Run the script

From the repo root:

```bash
# Read from a specific file (e.g. filtered list or custom path)
python .github/skills/resolve-pr-threads/scripts/resolve_pr_threads.py --input filtered_pr_comments.json

# Read comment list from stdin (e.g. pipe from fetch --stdout)
python .github/skills/fetch-pr-comments/scripts/fetch_pr_comments.py --stdout | python .github/skills/resolve-pr-threads/scripts/resolve_pr_threads.py --stdin

# Resolve only specific comment IDs
python .github/skills/resolve-pr-threads/scripts/resolve_pr_threads.py 111111 222222
```

## Requirements

One of the following must be available:
- **`gh` CLI** — authenticated (`gh auth status` should pass), **or**
- **`GITHUB_TOKEN`** env var — personal access token with `repo` scope.

The token/CLI must have write access to the PR to resolve threads.

## Output

Prints a line per thread indicating success or failure:

```
  ✅ Resolved thread for comment 123456789
  ❌ Failed to resolve thread for comment 987654321: ...

Done: 3 resolved, 0 failed.
```

Exits with code `1` if any thread failed to resolve.

## Troubleshooting

| Error | Fix |
|-------|-----|
| `Input file not found` | Provide a comment list (e.g. run fetch-pr-comments, or pass `--input` / `--stdin`) |
| `Comment list contains no comment IDs` | Ensure the JSON array has objects with an `id` field |
| `No matching unresolved threads found` | Threads may already be resolved, or the comment IDs don't match the current PR |
| `No authentication method available` | Set `GITHUB_TOKEN` or run `gh auth login` |
