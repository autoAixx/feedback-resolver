---
name: fetch-pr-comments
description: Fetches inline GitHub PR review comments for the current branch and saves them to pr_comments.json. Tries gh CLI first, falls back to GitHub REST API via GITHUB_TOKEN. Use when you need to retrieve, pull, or load PR review comments or inline feedback from GitHub.
---

# Fetch PR Comments

Produces `pr_comments.json` in the repo root with the structure:
```json
[{ "id": 123456789, "file": "src/foo.ts", "line": 42, "comment": "..." }, ...]
```

- `id` — GitHub's numeric comment ID (used by the `resolve-pr-threads` skill to look up and resolve threads).
- `line` — line number in the file the comment was left on (`null` if GitHub did not provide one).

## Run the script

From the repo root:

```bash
python .github/skills/fetch-pr-comments/scripts/fetch_pr_comments.py
```

## Requirements

One of the following must be available:
- **`gh` CLI** — authenticated (`gh auth status` should pass), **or**
- **`GITHUB_TOKEN`** env var — personal access token with `repo` read scope.

## Troubleshooting

| Error | Fix |
|-------|-----|
| `gh CLI failed and GITHUB_TOKEN is not set` | Set `GITHUB_TOKEN` or run `gh auth login` |
| `Could not find open PR for current branch` | Ensure there is an open PR for your branch on GitHub |
| `Could not determine owner/repo` | Check that `git remote get-url origin` returns a valid GitHub URL |

## Output notes

- Only **inline review comments** are fetched (not the top-level PR description).
- Duplicate entries (same file + same body) are removed automatically.
