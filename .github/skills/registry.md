# Skill registry

Use skills **by name**. Each skill lives in `.github/skills/<name>/SKILL.md` — read that file for how to run it and what it does.

| Name | Purpose |
|------|--------|
| fetch-pr-comments | Fetch inline PR review comments for the current branch (output: file or stdout) |
| resolve-pr-threads | Resolve GitHub PR review threads (input: file, stdin, or comment IDs) |
| build-project | Build the project (if present) |
| run-tests | Run tests (if present) |

You are free to pass data between steps via files (any path), stdin/stdout, or in-context — use whatever fits the workflow.
