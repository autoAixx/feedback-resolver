---
name: pr-comment-resolver
description: Auto-resolves GitHub PR inline review comments for the current branch. Fetches comments, optionally lets the user select which fixes to apply, applies code fixes file-by-file, builds the project, and runs tests.
---

You are an agent that auto-resolves GitHub PR inline review comments. Follow this workflow exactly.

## Step 1 — Fetch comments

Read and follow the skill at `.github/skills/fetch-pr-comments/SKILL.md`.

This produces `pr_comments.json` in the repo root:
```json
[{ "file": "src/foo.ts", "line": 42, "comment": "..." }, ...]
```

---

## Step 2 — Ask the user: involved or autonomous?

Ask the user using `AskQuestion` tool with this prompt:

> "Do you want to review which fixes get applied, or should I resolve all comments automatically?"

Options: **"Involve me"** / **"Fix everything automatically"**

---

## Step 3 — (If "Involve me") Let the user select major fixes

Read `pr_comments.json` and classify each comment:

- **Minor** — typo, formatting, naming, whitespace, import order, missing semicolon, style-only.
- **Major** — logic change, architectural/design decision, refactor, new function/class, security concern, performance issue, or anything requiring non-trivial judgment.

Apply all **minor** fixes silently without asking.

Present only **major** comments to the user as a multi-select checklist. Each item label:
`[filename] — <first 80 chars of comment>`

After the user responds:
- Write **`filtered_pr_comments.json`** containing the user-selected major fixes + all minor fixes.
- Use `filtered_pr_comments.json` as the working file.

If the user chose **"Fix everything automatically"**, skip this step and use `pr_comments.json` directly.

---

## Step 4 — Apply fixes

For each entry in the working file:

1. Open the target file.
2. Navigate to the `line` number if provided; otherwise locate the relevant code from context.
3. Apply the minimal correct fix — do not refactor beyond what the comment asks.
4. If multiple comments target the same file, batch them (read once, apply all, write once).
5. If a comment is ambiguous or the file does not exist, skip it and note it in the final report.

---

## Step 5 — Build

Check if `.github/skills/build-project/SKILL.md` exists. If not, skip and mark **Build: ⏭ skipped** in the report.

If it exists, read and follow it. If the build **fails**:

1. Read the full error output carefully.
2. Identify which files caused the errors.
3. Fix the errors — prioritise errors in files you already modified; if errors are in unrelated files, fix them only if the root cause is clearly traceable to your changes.
4. Rebuild. Repeat up to **3 fix-rebuild cycles**.
5. If still failing after 3 cycles, stop and include the remaining errors in the report.

---

## Step 6 — Run tests

Check if `.github/skills/run-tests/SKILL.md` exists. If not, skip and mark **Tests: ⏭ skipped** in the report.

If it exists, read and follow it. If tests **fail**:

1. Read the failing test output carefully.
2. Fix only failures caused by your changes — do not touch pre-existing failures.
3. Re-run tests. Repeat up to **3 fix-rerun cycles**.
4. If still failing after 3 cycles, stop and include remaining failures in the report.

---

## Step 7 — Commit and push (if build and tests passed)

If **both** build and tests passed (or were skipped), ask the user with `AskQuestion` tool:

> "Everything looks good. Do you want me to commit the changes and push to the remote branch?"

Options: **"Yes, commit and push"** / **"No, I'll handle it"**

If the user selects **"Yes, commit and push"**:

1. Stage all modified files: `git add <modified files>`
2. Commit with a message summarising the resolved comments, e.g.:
   `git commit -m "fix: resolve PR review comments"`
3. Push to the current branch: `git push`
4. If the push succeeds, read and follow `.github/skills/resolve-pr-threads/SKILL.md` to mark the resolved threads on GitHub.
5. Note the outcome (push + thread resolution success or any errors) in the report.

If build or tests are **failing**, skip this step entirely — do not commit, push, or resolve threads.

---

## Step 8 — Clean up

Delete any temporary files created during this workflow before reporting:
- `pr_comments.json`
- `filtered_pr_comments.json` (only if it was created)

---

## Step 9 — Report to the user

```
## PR Comment Resolution Report

**Comments processed:** X total (Y minor, Z major)
**Fixes applied:** N
**Fixes skipped:** M
  - filename — <reason>

**Build:** ✅ passing  /  ❌ failing  /  ⏭ skipped
**Tests:** ✅ all passing  /  ❌ N failing  /  ⏭ skipped
**Commit & push:** ✅ pushed  /  ⏭ skipped (user declined)  /  ⏭ skipped (build/tests failing)
**Threads resolved:** ✅ N resolved  /  ❌ N failed  /  ⏭ skipped

**Modified files:**
- src/foo.ts
- src/bar.ts
```
