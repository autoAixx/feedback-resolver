---
name: resolve-pr-threads
description: Marks GitHub PR review threads as resolved via the GitHub GraphQL API. Reads comment IDs from pr_comments.json (produced by fetch-pr-comments skill) and resolves their corresponding threads. Use after applying fixes to a PR branch.
---

# Resolve PR Threads

Resolves GitHub PR review threads by reading comment IDs from `pr_comments.json`, querying GitHub GraphQL to map them to thread node IDs, then calling `resolveReviewThread` for each.

> **Prerequisite:** `pr_comments.json` must exist in the repo root. Run the `fetch-pr-comments` skill first if it does not.

## Run the script

From the repo root:

```bash
python .github/skills/resolve-pr-threads/scripts/resolve_pr_threads.py
```

To resolve specific comments only (by their numeric GitHub comment IDs):

```bash
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
| `pr_comments.json not found` | Run the `fetch-pr-comments` skill first |
| `pr_comments.json contains no comment IDs` | Ensure you are using the latest version of the fetch skill |
| `No matching unresolved threads found` | Threads may already be resolved, or the comment IDs don't match the current PR |
| `No authentication method available` | Set `GITHUB_TOKEN` or run `gh auth login` |
