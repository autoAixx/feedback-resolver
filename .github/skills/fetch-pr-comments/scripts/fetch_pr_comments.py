#!/usr/bin/env python3
"""
Fetch inline PR review comments for the current branch.
Outputs a JSON array [{id, file, line, comment}] to a file or stdout.

Priority: gh CLI -> GitHub REST API (GITHUB_TOKEN)

Usage:
  python fetch_pr_comments.py (--output FILE | --stdout) [--debug]
  --output FILE   write JSON to FILE
  --stdout        write JSON to stdout (no file)
  --debug         print debug diagnostics to stderr
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.request
import urllib.error
import urllib.parse


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


def get_current_pr_number_via_api(owner, repo, token, debug: bool = False):
    """Find open PR for the current branch via API."""
    def dbg(msg: str) -> None:
        if debug:
            print(f"DEBUG: {msg}", file=sys.stderr)

    code, branch, _ = run("git rev-parse --abbrev-ref HEAD")
    if code != 0:
        dbg("Failed to read current branch via git.")
        return None
    branch = branch.strip()
    head = f"{owner}:{branch}"
    # URL-encode the head parameter (branches often include '/')
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls?head={urllib.parse.quote(head, safe='')}&state=open"
    dbg(f"Looking up open PR via API. branch={branch!r} head={head!r}")
    dbg(f"GET {url}")
    try:
        req = urllib.request.Request(url, headers={"Authorization": f"token {token}", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req) as resp:
            raw = resp.read()
            dbg(f"HTTP {getattr(resp, 'status', 'unknown')} bytes={len(raw)}")
            data = json.loads(raw)

            if isinstance(data, dict):
                # GitHub error responses are objects like {"message": "...", ...}
                dbg(f"Unexpected object response: keys={list(data.keys())[:10]}")
                dbg(f"message={data.get('message')!r} documentation_url={data.get('documentation_url')!r}")
                return None

            if not isinstance(data, list):
                dbg(f"Unexpected response type: {type(data).__name__}")
                return None

            if not data:
                dbg("No open PRs returned for this head filter.")
                return None

            pr_number = data[0].get("number")
            dbg(f"Matched PR number: {pr_number!r}")
            return str(pr_number) if pr_number else None
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            body = "<unreadable>"
        status = getattr(e, "code", None)
        dbg(f"HTTPError status={status} body={body[:1000]!r}")
        if status == 401:
            print(
                "ERROR: GitHub API returned 401 Unauthorized while looking up the PR. "
                "Check that GITHUB_TOKEN is set, valid, and has repo read access, or log in via gh.",
                file=sys.stderr,
            )
        return None
    except Exception as e:
        dbg(f"Exception during PR lookup: {type(e).__name__}: {e}")
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
    parser = argparse.ArgumentParser(description="Fetch PR review comments for the current branch.")
    output_group = parser.add_mutually_exclusive_group(required=True)
    output_group.add_argument("--output", "-o", help="Output file path")
    output_group.add_argument("--stdout", action="store_true", help="Write JSON to stdout instead of a file")
    parser.add_argument("--debug", action="store_true", help="Print debug diagnostics to stderr")
    args = parser.parse_args()

    def dbg(msg: str) -> None:
        if args.debug:
            print(f"DEBUG: {msg}", file=sys.stderr)

    # --- Try gh CLI first ---
    code, _, _ = run("gh --version")
    gh_available = (code == 0)
    dbg(f"gh_available={gh_available}")

    owner = repo = pr_number = None
    raw_comments = None

    if gh_available:
        info = get_pr_info_via_gh()
        if info:
            owner, repo, pr_number = info
            dbg(f"Using gh CLI. owner={owner} repo={repo} pr={pr_number}")
            raw_comments = fetch_comments_via_gh(pr_number)
            if raw_comments is not None:
                dbg(f"Fetched {len(raw_comments)} raw comment(s) via gh CLI")

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
        dbg(f"Using REST API. owner={owner} repo={repo}")
        pr_number = get_current_pr_number_via_api(owner, repo, token, debug=args.debug)
        if not pr_number:
            print("ERROR: Could not find open PR for the current branch.", file=sys.stderr)
            sys.exit(1)
        dbg(f"Detected PR number via API: pr={pr_number}")
        raw_comments = fetch_comments_via_api(owner, repo, pr_number, token)
        if raw_comments is not None:
            dbg(f"Fetched {len(raw_comments)} raw comment(s) via REST API")

    if raw_comments is None:
        print("ERROR: Failed to fetch PR comments.", file=sys.stderr)
        sys.exit(1)

    comments = parse_comments(raw_comments)
    dbg(f"Parsed {len(comments)} inline comment(s) after filtering/dedup")

    if args.stdout:
        dbg("Writing JSON to stdout")
        json.dump(comments, sys.stdout, indent=2, ensure_ascii=False)
        print(file=sys.stdout)
    else:
        dbg(f"Writing JSON to file: {args.output}")
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(comments, f, indent=2, ensure_ascii=False)
        print(f"Wrote {len(comments)} comment(s) to {args.output}")


if __name__ == "__main__":
    main()
