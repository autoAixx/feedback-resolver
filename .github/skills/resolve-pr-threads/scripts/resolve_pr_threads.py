#!/usr/bin/env python3
"""
Mark GitHub PR review threads as resolved.

Reads comment IDs from a provided JSON list (file or stdin) or from explicit IDs,
maps them to GraphQL thread node IDs, then calls resolveReviewThread for each.

Priority: gh CLI -> GITHUB_TOKEN

Usage:
    python resolve_pr_threads.py --input FILE         # read comment list from FILE (JSON array with id)
    python resolve_pr_threads.py --stdin              # read comment list from stdin (JSON array)
    python resolve_pr_threads.py 111 222 333          # resolve only these comment IDs
    python resolve_pr_threads.py ... --debug          # print debug diagnostics to stderr
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
import urllib.error
import urllib.parse


def run(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


THREADS_QUERY = """
query($owner: String!, $repo: String!, $pr: Int!, $after: String) {
    repository(owner: $owner, name: $repo) {
        pullRequest(number: $pr) {
            reviewThreads(first: 100, after: $after) {
                nodes {
                    id
                    isResolved
                    comments(first: 100) {
                        nodes {
                            databaseId
                        }
                        pageInfo {
                            endCursor
                            hasNextPage
                        }
                    }
                }
                pageInfo {
                    endCursor
                    hasNextPage
                }
            }
        }
    }
}
"""

THREAD_COMMENTS_QUERY = """
query($threadId: ID!, $after: String) {
    node(id: $threadId) {
        ... on PullRequestReviewThread {
            comments(first: 100, after: $after) {
                nodes {
                    databaseId
                }
                pageInfo {
                    endCursor
                    hasNextPage
                }
            }
        }
    }
}
"""

RESOLVE_MUTATION = """
mutation($threadId: ID!) {
  resolveReviewThread(input: { threadId: $threadId }) {
    thread {
      id
      isResolved
    }
  }
}
"""


def graphql_request(query, variables, gh_available, token):
    """Run a GraphQL query/mutation, trying gh CLI first then GITHUB_TOKEN."""
    if gh_available:
        payload = json.dumps({"query": query, "variables": variables})
        # Write to a temp file — avoids all shell escaping issues with $ in GraphQL queries
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            f.write(payload)
            tmp_path = f.name
        try:
            result = subprocess.run(
                ["gh", "api", "graphql", "--input", tmp_path],
                capture_output=True,
                text=True,
            )
        finally:
            os.unlink(tmp_path)
        if result.returncode == 0:
            try:
                data = json.loads(result.stdout)
                if not data.get("errors"):
                    return data, None
            except Exception:
                pass

    if token:
        body = json.dumps({"query": query, "variables": variables}).encode("utf-8")
        try:
            req = urllib.request.Request(
                "https://api.github.com/graphql",
                data=body,
                headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read())
                return data, data.get("errors")
        except Exception as e:
            return None, str(e)

    return None, "No authentication method available"


def get_pr_info_via_gh():
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
    code, out, _ = run("git remote get-url origin")
    if code != 0:
        return None
    url = out.strip()
    url = url.replace("git@github.com:", "").replace("https://github.com/", "").removesuffix(".git")
    parts = url.split("/")
    if len(parts) < 2:
        return None
    return parts[0], parts[1]


def get_current_pr_number_via_api(owner, repo, token, debug: bool = False):
    def dbg(msg: str) -> None:
        if debug:
            print(f"DEBUG: {msg}", file=sys.stderr)

    code, branch, _ = run("git rev-parse --abbrev-ref HEAD")
    if code != 0:
        dbg("Failed to read current branch via git.")
        return None
    branch = branch.strip()
    head = f"{owner}:{branch}"
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
                "Check that GITHUB_TOKEN is set, valid, and has repo access, or log in via gh.",
                file=sys.stderr,
            )
        return None
    except Exception as e:
        dbg(f"Exception during PR lookup: {type(e).__name__}: {e}")
        return None


def load_comment_ids(cli_ids, input_path, read_stdin):
    """Return set of comment database IDs to resolve.
    cli_ids: list of numeric IDs from argv; if non-empty, use only these.
    input_path: path to JSON file (array of {id, ...}); used if cli_ids is empty and not read_stdin.
    read_stdin: if True, read JSON array from stdin.
    """
    if cli_ids:
        ids = set()
        for i in cli_ids:
            try:
                ids.add(int(i))
            except ValueError:
                print(f"ERROR: Invalid comment ID '{i}'. Expected an integer.", file=sys.stderr)
                sys.exit(1)
        return ids

    if read_stdin:
        try:
            comments = json.load(sys.stdin)
        except json.JSONDecodeError as e:
            print(f"ERROR: Invalid JSON from stdin: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        if not input_path:
            print("ERROR: No input provided. Use --input FILE, --stdin, or provide explicit IDs.", file=sys.stderr)
            sys.exit(1)
        try:
            with open(input_path, encoding="utf-8") as f:
                comments = json.load(f)
        except FileNotFoundError:
            print(f"ERROR: Input file not found: {input_path}. Provide a comment list (e.g. run fetch-pr-comments first).", file=sys.stderr)
            sys.exit(1)

    if not isinstance(comments, list):
        print("ERROR: Input must be a JSON array of comment objects with 'id'.", file=sys.stderr)
        sys.exit(1)
    ids = {c["id"] for c in comments if c.get("id")}
    if not ids:
        print("ERROR: Comment list contains no comment IDs.", file=sys.stderr)
        sys.exit(1)
    return ids


def fetch_review_threads(owner, repo, pr_number, gh_available, token):
    """Return all review threads for a PR, handling pagination."""
    threads = []
    after = None
    while True:
        variables = {"owner": owner, "repo": repo, "pr": int(pr_number), "after": after}
        result, err = graphql_request(THREADS_QUERY, variables, gh_available, token)
        if not result:
            print(f"ERROR: Failed to fetch review threads: {err}", file=sys.stderr)
            sys.exit(1)

        review_threads = (
            result.get("data", {})
            .get("repository", {})
            .get("pullRequest", {})
            .get("reviewThreads", {})
        )

        nodes = review_threads.get("nodes", [])
        threads.extend(nodes)

        page_info = review_threads.get("pageInfo", {})
        if not page_info.get("hasNextPage"):
            break
        after = page_info.get("endCursor")
    return threads


def fetch_thread_comments(thread_id, gh_available, token, after=None):
    """Return all comments for a review thread, handling pagination."""
    comments = []
    cursor = after
    while True:
        variables = {"threadId": thread_id, "after": cursor}
        result, err = graphql_request(THREAD_COMMENTS_QUERY, variables, gh_available, token)
        if not result:
            print(f"ERROR: Failed to fetch thread comments: {err}", file=sys.stderr)
            sys.exit(1)

        thread_node = (result.get("data", {}) or {}).get("node") or {}
        comment_data = thread_node.get("comments") or {}

        comments.extend(comment_data.get("nodes", []))
        page_info = comment_data.get("pageInfo", {})
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")
    return comments


def fetch_thread_map(owner, repo, pr_number, gh_available, token):
    """Return dict mapping comment database ID -> thread node ID for unresolved threads."""
    threads = fetch_review_threads(owner, repo, pr_number, gh_available, token)

    thread_map = {}
    for thread in threads:
        if thread.get("isResolved"):
            continue
        comment_data = thread.get("comments") or {}
        comment_nodes = comment_data.get("nodes", [])
        page_info = comment_data.get("pageInfo", {})

        if page_info.get("hasNextPage"):
            comment_nodes.extend(
                fetch_thread_comments(
                    thread["id"],
                    gh_available,
                    token,
                    after=page_info.get("endCursor"),
                )
            )

        for comment in comment_nodes:
            db_id = comment.get("databaseId")
            if db_id:
                thread_map[db_id] = thread["id"]
    return thread_map


def main():
    parser = argparse.ArgumentParser(description="Resolve GitHub PR review threads by comment IDs.")
    input_group = parser.add_mutually_exclusive_group()
    input_group.add_argument("--input", "-i", help="Path to JSON file with comment list")
    input_group.add_argument("--stdin", action="store_true", help="Read comment list (JSON array) from stdin")
    parser.add_argument("--debug", action="store_true", help="Print debug diagnostics to stderr")
    parser.add_argument("ids", nargs="*", help="Optional: resolve only these comment IDs")
    args = parser.parse_args()

    def dbg(msg: str) -> None:
        if args.debug:
            print(f"DEBUG: {msg}", file=sys.stderr)

    if not args.ids and not args.stdin and not args.input:
        print("ERROR: Provide --input FILE, --stdin, or one or more comment IDs.", file=sys.stderr)
        sys.exit(2)

    comment_ids = load_comment_ids(args.ids, args.input, args.stdin)
    dbg(f"Loaded {len(comment_ids)} comment ID(s)")

    code, _, _ = run("gh --version")
    gh_available = code == 0
    token = os.environ.get("GITHUB_TOKEN")
    dbg(f"gh_available={gh_available} token_available={bool(token)}")

    if not gh_available and not token:
        print("ERROR: gh CLI not available and GITHUB_TOKEN is not set.", file=sys.stderr)
        sys.exit(1)

    owner = repo = pr_number = None
    if gh_available:
        info = get_pr_info_via_gh()
        if info:
            owner, repo, pr_number = info
            dbg(f"Using gh CLI. owner={owner} repo={repo} pr={pr_number}")

    if not pr_number:
        git_info = get_pr_info_via_git()
        if not git_info:
            print("ERROR: Could not determine owner/repo from git remote.", file=sys.stderr)
            sys.exit(1)
        owner, repo = git_info
        dbg(f"Using git+API. owner={owner} repo={repo}")
        pr_number = get_current_pr_number_via_api(owner, repo, token, debug=args.debug)
        if not pr_number:
            print("ERROR: Could not find open PR for the current branch.", file=sys.stderr)
            sys.exit(1)
        dbg(f"Detected PR number via API: pr={pr_number}")

    thread_map = fetch_thread_map(owner, repo, pr_number, gh_available, token)
    dbg(f"Fetched unresolved thread map entries: {len(thread_map)}")

    to_resolve = {db_id: thread_map[db_id] for db_id in comment_ids if db_id in thread_map}
    dbg(f"Threads to resolve (intersection): {len(to_resolve)}")

    if not to_resolve:
        print("No matching unresolved threads found for the given comment IDs.")
        return

    resolved = []
    failed = []
    for db_id, thread_id in to_resolve.items():
        data, err = graphql_request(RESOLVE_MUTATION, {"threadId": thread_id}, gh_available, token)
        if data and not err:
            resolved.append(db_id)
            print(f"  ✅ Resolved thread for comment {db_id}")
        else:
            failed.append(db_id)
            print(f"  ❌ Failed to resolve thread for comment {db_id}: {err}", file=sys.stderr)

    print(f"\nDone: {len(resolved)} resolved, {len(failed)} failed.")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
