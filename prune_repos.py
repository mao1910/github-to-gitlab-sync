#!/usr/bin/env python3
"""
prune_repos.py

Identifies and deletes stale GitLab mirror projects that no longer exist on GitHub,
with a configurable grace period and dry-run mode.
"""

import os
import requests
import json
from datetime import datetime, timedelta, timezone

# ──────────────────────────────────────────────────────────────────────────────
# Configuration via environment variables (set in the CI workflow)
# ──────────────────────────────────────────────────────────────────────────────
GITHUB_TOKEN     = os.environ["GITHUB_TOKEN"]               # GitHub PAT for listing repos
GITLAB_TOKEN     = os.environ["GITLAB_TOKEN"]               # GitLab PAT for API operations
GITLAB_URL       = os.environ.get("GITLAB_URL", "https://gitlab.com")
GITLAB_GROUP_ID  = os.environ["GITLAB_GROUP_ID"]            # Numeric ID of the target GitLab group
GITHUB_USER      = os.environ["GITHUB_USER"]                # Comma-separated GitHub usernames
DRY_RUN          = os.environ.get("DRY_RUN", "true").lower() == "true"
GRACE_DAYS       = int(os.environ.get("GRACE_DAYS", "7"))   # Days to wait before actual deletion
EXCLUDE          = set(os.environ.get("PRUNE_EXCLUDE", "mirror-scripts").split(","))
STATE_FILE       = "prune_state.json"                       # Local cache of last-seen timestamps

# Prepare HTTP headers for GitLab and GitHub API calls
gl_headers = {"PRIVATE-TOKEN": GITLAB_TOKEN}
gh_headers = {"Authorization": f"token {GITHUB_TOKEN}"}


def list_gitlab_projects():
    """
    Retrieve all projects in the GitLab group.
    Returns: dict mapping project name to project ID.
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
            break  # no more pages
        for p in data:
            projects[p["name"]] = p["id"]
        page += 1
    return projects


def fetch_github_repos():
    """
    Fetch all GitHub repos visible to the PAT, including private, owned, and public forks.
    Returns: set of repository names.
    """
    # Handle multiple GitHub usernames for public repos
    owners = [u.strip() for u in GITHUB_USER.split(",")]

    repos = set()
    page = 1

    while True:
        # 1) Private & owned repos via /user/repos
        r1 = requests.get(
            "https://api.github.com/user/repos",
            headers=gh_headers,
            params={"per_page": 100, "page": page, "type": "all", "sort": "updated"}
        )
        r1.raise_for_status()
        data1 = r1.json()

        # 2) Public & forked repos under each specified owner
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
            break  # no more repos to fetch on this page

        repos.update(combined)
        page += 1

    return repos


def load_state():
    """
    Load last-seen timestamps from the state file.
    Returns: dict of project name to ISO timestamp.
    """
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}  # start fresh if no state file exists


def save_state(state):
    """
    Save the updated last-seen timestamps to the state file.
    """
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def prune_deleted_repos():
    """
    Main logic to detect and delete (or dry-run) stale projects:
      1) Fetch current GitHub repos and existing GitLab projects
      2) Update 'last seen' for projects still present or excluded
      3) Identify projects missing on GitHub and beyond the grace period
      4) Delete them if DRY_RUN is false, otherwise list them
    """
    gh_names = fetch_github_repos()
    gl_projects = list_gitlab_projects()
    state = load_state()
    now = datetime.now(timezone.utc)

    # Refresh 'last seen' for still-active or excluded projects
    for name in gl_projects:
        if name in gh_names or name in EXCLUDE:
            state[name] = now.isoformat()

    to_delete = []
    for name, proj_id in gl_projects.items():
        if name in gh_names or name in EXCLUDE:
            continue  # skip active or protected projects

        last_seen_iso = state.get(name)
        if last_seen_iso:
            last_seen = datetime.fromisoformat(last_seen_iso)
            # If missing longer than GRACE_DAYS, mark for deletion
            if now - last_seen >= timedelta(days=GRACE_DAYS):
                to_delete.append((name, proj_id))
        else:
            # First time detected as missing
            if GRACE_DAYS == 0:
                to_delete.append((name, proj_id))
            state[name] = now.isoformat()

    # Persist updated state for next run
    save_state(state)

    # Perform deletion or dry-run reporting
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
