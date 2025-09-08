#!/usr/bin/env python3
"""
prune_repos.py

Identifies and deletes stale GitLab mirror projects that no longer exist on GitHub,
with a configurable grace period and dry-run mode.
"""

import os
import requests
import json
from datetime import datetime, timedelta

# ──────────────────────────────────────────────────────────────────────────────
# Configuration via environment variables
# ──────────────────────────────────────────────────────────────────────────────
GITHUB_TOKEN     = os.environ["GITHUB_TOKEN"]       # GitHub PAT
GITLAB_TOKEN     = os.environ["GITLAB_TOKEN"]       # GitLab PAT
GITLAB_URL       = os.environ.get("GITLAB_URL", "https://gitlab.com")
GITLAB_GROUP_ID  = os.environ["GITLAB_GROUP_ID"]    # Numeric GitLab group ID
GITHUB_USER      = os.environ["GITHUB_USER"]        # Comma-separated GitHub usernames
DRY_RUN          = os.environ.get("DRY_RUN", "true").lower() == "true"
GRACE_DAYS       = int(os.environ.get("GRACE_DAYS", "7"))
EXCLUDE          = set(os.environ.get("PRUNE_EXCLUDE", "mirror-scripts").split(","))
STATE_FILE       = "prune_state.json"
# ──────────────────────────────────────────────────────────────────────────────

gl_headers = {"PRIVATE-TOKEN": GITLAB_TOKEN}
gh_headers = {"Authorization": f"token {GITHUB_TOKEN}"}


def list_gitlab_projects():
    """
    Return dict of project_name → project_id for all projects in the GitLab group.
    """
    projects = {}
    page = 1
    while True:
        resp = requests.get(
            f"{GITLAB_URL}/api/v4/groups/{GITLAB_GROUP_ID}/projects",
            headers=gl_headers,
            params={"per_page": 100, "page": page}
        )
        resp.raise_for_status()
        data = resp.json()
        if not data:
            break
        for p in data:
            projects[p["name"]] = p["id"]
        page += 1
    return projects


def fetch_github_repos():
    """
    Fetch all GitHub repos visible to the PAT (private & owned + public forks).
    Returns a set of repo names.
    """
    # Support multiple GitHub usernames for public repos
    owners = [u.strip() for u in GITHUB_USER.split(",")]

    repos = set()
    page = 1

    while True:
        # private & owned repos
        r1 = requests.get(
            "https://api.github.com/user/repos",
            headers=gh_headers,
            params={"per_page": 100, "page": page, "type": "all", "sort": "updated"}
        )
        r1.raise_for_status()
        data1 = r1.json()

        # public (including forks) under each specified owner
        data2 = []
        for owner in owners:
            r2 = requests.get(
                f"https://api.github.com/users/{owner}/repos",
                headers=gh_headers,
                params={"per_page": 100, "page": page, "type": "all", "sort": "updated"}
            )
            r2.raise_for_status()
            data2.extend(r2.json())

        combined = {repo["name"] for repo in (data1 + data2)}
        if not combined:
            break

        repos.update(combined)
        page += 1

    return repos


def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def prune_deleted_repos():
    gh_names = fetch_github_repos()
    gl_projects = list_gitlab_projects()
    state = load_state()
    now = datetime.utcnow()

    # Update last-seen for existing or excluded projects
    for name in gl_projects:
        if name in gh_names or name in EXCLUDE:
            state[name] = now.isoformat()

    to_delete = []
    for name, proj_id in gl_projects.items():
        if name in gh_names or name in EXCLUDE:
            continue
        last_seen_iso = state.get(name)
        if last_seen_iso:
            last_seen = datetime.fromisoformat(last_seen_iso)
            if now - last_seen >= timedelta(days=GRACE_DAYS):
                to_delete.append((name, proj_id))
        else:
            # First detection of deletion – record or delete immediately if GRACE_DAYS is 0
            if GRACE_DAYS == 0:
                to_delete.append((name, proj_id))
            state[name] = now.isoformat()

    save_state(state)

    # Report or delete stale projects
    for name, proj_id in to_delete:
        if DRY_RUN:
            print(f"[DRY RUN] Would delete '{name}' (project ID {proj_id})")
        else:
            print(f"Deleting '{name}' (project ID {proj_id})…", end=" ")
            resp = requests.delete(
                f"{GITLAB_URL}/api/v4/projects/{proj_id}", headers=gl_headers
            )
            resp.raise_for_status()
            print("Done.")


if __name__ == "__main__":
    prune_deleted_repos()
