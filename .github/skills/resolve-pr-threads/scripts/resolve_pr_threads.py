#!/usr/bin/env python3
"""
Mark GitHub PR review threads as resolved.

Reads comment IDs from pr_comments.json (produced by fetch-pr-comments skill),
maps them to GraphQL thread node IDs, then calls resolveReviewThread for each.

Priority: gh CLI -> GITHUB_TOKEN

Usage:
    python resolve_pr_threads.py                  # resolves all threads in pr_comments.json
    python resolve_pr_threads.py 111 222 333      # resolves threads for specific comment IDs only
"""

import json
import os
import subprocess
import sys
import tempfile
import urllib.request


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


def get_current_pr_number_via_api(owner, repo, token):
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


def load_comment_ids(args):
    """Return set of comment database IDs to resolve."""
    if args:
        ids = set()
        for i in args:
            try:
                ids.add(int(i))
            except ValueError:
                print(f"ERROR: Invalid comment ID '{i}'. Expected an integer.", file=sys.stderr)
                sys.exit(1)
        return ids
    try:
        with open("pr_comments.json", encoding="utf-8") as f:
            comments = json.load(f)
    except FileNotFoundError:
        print("ERROR: pr_comments.json not found. Run the fetch-pr-comments skill first.", file=sys.stderr)
        sys.exit(1)
    ids = {c["id"] for c in comments if c.get("id")}
    if not ids:
        print("ERROR: pr_comments.json contains no comment IDs.", file=sys.stderr)
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
    comment_ids = load_comment_ids(sys.argv[1:])

    code, _, _ = run("gh --version")
    gh_available = code == 0
    token = os.environ.get("GITHUB_TOKEN")

    if not gh_available and not token:
        print("ERROR: gh CLI not available and GITHUB_TOKEN is not set.", file=sys.stderr)
        sys.exit(1)

    owner = repo = pr_number = None
    if gh_available:
        info = get_pr_info_via_gh()
        if info:
            owner, repo, pr_number = info

    if not pr_number:
        git_info = get_pr_info_via_git()
        if not git_info:
            print("ERROR: Could not determine owner/repo from git remote.", file=sys.stderr)
            sys.exit(1)
        owner, repo = git_info
        pr_number = get_current_pr_number_via_api(owner, repo, token)
        if not pr_number:
            print("ERROR: Could not find open PR for the current branch.", file=sys.stderr)
            sys.exit(1)

    thread_map = fetch_thread_map(owner, repo, pr_number, gh_available, token)

    to_resolve = {db_id: thread_map[db_id] for db_id in comment_ids if db_id in thread_map}

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
