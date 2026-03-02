#!/usr/bin/env python3
"""
Fetch inline PR review comments for the current branch.
Outputs pr_comments.json with [{id, file, line, comment}] in the repo root.

Priority: gh CLI -> GitHub REST API (GITHUB_TOKEN)
"""

import json
import os
import subprocess
import sys
import urllib.request
import urllib.error


def run(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def get_pr_info_via_gh():
    """Returns (owner, repo, pr_number) using gh CLI."""
    code, out, _ = run("gh repo view --json owner,name --jq \"{owner:.owner.login,repo:.name}\"")
    if code != 0:
        return None
    try:
        data = json.loads(out)
        owner = data.get("owner", "")
        repo = data.get("repo", "")
    except Exception:
        return None

    code, number, _ = run("gh pr view --json number --jq .number")
    if code != 0 or not number:
        return None

    if not owner or not repo:
        return None
    return owner, repo, number.strip()


def get_pr_info_via_git():
    """Derive owner/repo from git remote origin URL."""
    code, out, _ = run("git remote get-url origin")
    if code != 0:
        return None
    url = out.strip()
    # Handles both HTTPS and SSH formats
    url = url.replace("git@github.com:", "").replace("https://github.com/", "").removesuffix(".git")
    parts = url.split("/")
    if len(parts) < 2:
        return None
    return parts[0], parts[1]


def get_current_pr_number_via_api(owner, repo, token):
    """Find open PR for the current branch via API."""
    code, branch, _ = run("git rev-parse --abbrev-ref HEAD")
    if code != 0:
        return None
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls?head={owner}:{branch}&state=open"
    try:
        req = urllib.request.Request(url, headers={"Authorization": f"token {token}", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
            return str(data[0]["number"]) if data else None
    except Exception:
        return None


def fetch_comments_via_gh(pr_number):
    code, out, _ = run(f"gh api repos/{{owner}}/{{repo}}/pulls/{pr_number}/comments --paginate")
    if code != 0:
        return None
    return json.loads(out)


def fetch_comments_via_api(owner, repo, pr_number, token):
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/comments?per_page=100"
    try:
        req = urllib.request.Request(url, headers={"Authorization": f"token {token}", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"API error: {e}", file=sys.stderr)
        return None


def parse_comments(raw):
    """Extract file path, line number, and comment body. Skips outdated comments."""
    seen = set()
    result = []
    for c in raw:
        # position is null when the comment is outdated (the referenced code changed)
        if c.get("position") is None:
            continue
        path = c.get("path", "")
        body = c.get("body", "").strip()
        # prefer original_line, fall back to line
        line = c.get("original_line") or c.get("line")
        if not body or not path:
            continue
        key = (path, line, body)
        if key in seen:
            continue
        seen.add(key)
        entry = {"id": c.get("id"), "file": path, "line": line, "comment": body}
        result.append(entry)
    return result


def main():
    output_file = "pr_comments.json"

    # --- Try gh CLI first ---
    code, _, _ = run("gh --version")
    gh_available = (code == 0)

    owner = repo = pr_number = None
    raw_comments = None

    if gh_available:
        info = get_pr_info_via_gh()
        if info:
            owner, repo, pr_number = info
            raw_comments = fetch_comments_via_gh(pr_number)

    # --- Fall back to REST API ---
    if raw_comments is None:
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            print("ERROR: gh CLI failed and GITHUB_TOKEN env var is not set.", file=sys.stderr)
            sys.exit(1)

        git_info = get_pr_info_via_git()
        if not git_info:
            print("ERROR: Could not determine owner/repo from git remote.", file=sys.stderr)
            sys.exit(1)
        owner, repo = git_info
        pr_number = get_current_pr_number_via_api(owner, repo, token)
        if not pr_number:
            print("ERROR: Could not find open PR for the current branch.", file=sys.stderr)
            sys.exit(1)
        raw_comments = fetch_comments_via_api(owner, repo, pr_number, token)

    if raw_comments is None:
        print("ERROR: Failed to fetch PR comments.", file=sys.stderr)
        sys.exit(1)

    comments = parse_comments(raw_comments)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(comments, f, indent=2, ensure_ascii=False)

    print(f"Wrote {len(comments)} comment(s) to {output_file}")


if __name__ == "__main__":
    main()
