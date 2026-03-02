---
name: fetch-pr-comments
description: Fetches inline GitHub PR review comments for the current branch. Output can be written to a file or stdout. Use when you need to retrieve, pull, or load PR review comments or inline feedback from GitHub.
---

# Fetch PR Comments

Fetches inline PR review comments for the current branch and outputs a JSON array. You must choose to write either to a file (explicit `--output`) or to stdout (`--stdout`) so the next step can use the data without relying on a default file.

**Output shape:** `[{ "id": 123456789, "file": "src/foo.ts", "line": 42, "comment": "..." }, ...]`

- `id` — GitHub's numeric comment ID (used when resolving threads).
- `line` — line number in the file (`null` if GitHub did not provide one).

## Run the script

From the repo root:

```bash
# Custom output path (e.g. temp or project-specific)
python .github/skills/fetch-pr-comments/scripts/fetch_pr_comments.py --output /path/to/comments.json

# Output to stdout (no file) — e.g. for piping or capturing in context
python .github/skills/fetch-pr-comments/scripts/fetch_pr_comments.py --stdout

# Debug diagnostics (prints to stderr; safe with --stdout)
python .github/skills/fetch-pr-comments/scripts/fetch_pr_comments.py --stdout --debug
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
