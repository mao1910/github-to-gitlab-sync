#!/usr/bin/env python3
"""
mirror_repos.py

Mirrors all GitHub repositories (private, owned, public forks) to a GitLab group.
"""

import os
import requests
import time
import sys

# ──────────────────────────────────────────────────────────────────────────────
# Required environment variables (set in GitHub Actions workflow 'env:' block)
# ──────────────────────────────────────────────────────────────────────────────
GITHUB_TOKEN       = os.getenv("GITHUB_TOKEN")       # GitHub PAT (repo scope)
GITLAB_TOKEN       = os.getenv("GITLAB_TOKEN")       # GitLab PAT (api+write_repository)
GITLAB_GROUP_ID    = os.getenv("GITLAB_GROUP_ID")    # Numeric GitLab group ID
GITLAB_GROUP_PATH  = os.getenv("GITLAB_GROUP_PATH")  # GitLab namespace path (string)
GITHUB_USER        = os.getenv("GITHUB_USER")        # Comma-separated GitHub usernames

# Exit if any required variable is missing
if not all([GITHUB_TOKEN, GITLAB_TOKEN, GITLAB_GROUP_ID, GITLAB_GROUP_PATH, GITHUB_USER]):
    print("[ERROR] Missing one of: GITHUB_TOKEN, GITLAB_TOKEN, GITLAB_GROUP_ID, "
          "GITLAB_GROUP_PATH, GITHUB_USER")
    sys.exit(1)

# HTTP headers for API calls
gh_headers = {"Authorization": f"token {GITHUB_TOKEN}"}
gl_headers = {"PRIVATE-TOKEN": GITLAB_TOKEN}
API_GH     = "https://api.github.com"       # Base URL for GitHub API
API_GL     = "https://gitlab.com/api/v4"    # Base URL for GitLab API

def fetch_repos():
    """
    Fetch all repos accessible to the authenticated GitHub user:
      1) Private & owned repos via /user/repos
      2) All public repos under the primary username via /users/{owner}/repos
    Combine and dedupe by full_name.
    Returns: list of (owner, name) tuples.
    """
    primary_owner = GITHUB_USER.split(",")[0].strip()
    page = 1
    repos = []

    while True:
        # 1) Private & owned repos
        resp1 = requests.get(
            f"{API_GH}/user/repos",
            headers=gh_headers,
            params={"per_page": 100, "page": page, "type": "all", "sort": "updated"}
        )
        resp1.raise_for_status()
        data1 = resp1.json()

        # 2) Public & forked repos under primary owner
        resp2 = requests.get(
            f"{API_GH}/users/{primary_owner}/repos",
            headers=gh_headers,
            params={"per_page": 100, "page": page, "type": "all", "sort": "updated"}
        )
        resp2.raise_for_status()
        data2 = resp2.json()

        # Combine and dedupe on full_name (owner/name)
        combined = {repo["full_name"]: repo for repo in (data1 + data2)}.values()
        if not combined:
            break

        for repo in combined:
            repos.append((repo["owner"]["login"], repo["name"]))

        page += 1

    return repos

def get_existing_project_id(name):
    """
    Search for an existing GitLab project under the group by name.
    Returns project ID if found, or None.
    """
    resp = requests.get(
        f"{API_GL}/groups/{GITLAB_GROUP_PATH}/projects",
        headers=gl_headers,
        params={"search": name}
    )
    resp.raise_for_status()
    for project in resp.json():
        if project["name"].lower() == name.lower():
            return project["id"]
    return None

def create_project(name, owner):
    """
    Create a new GitLab project under the group if it doesn't exist.
    Uses numeric GITLAB_GROUP_ID for namespace.
    Returns the project ID.
    """
    existing_id = get_existing_project_id(name)
    if existing_id:
        print(f"[INFO] '{name}' exists (ID {existing_id})")
        return existing_id

    payload = {
        "name":           name,
        "namespace_id":   int(GITLAB_GROUP_ID),
        "visibility":     "private",  # Change to "public" if desired
        "description":    f"Mirror of https://github.com/{owner}/{name}"
    }
    resp = requests.post(f"{API_GL}/projects", headers=gl_headers, data=payload)
    resp.raise_for_status()
    proj_id = resp.json()["id"]
    print(f"[INFO] Created '{name}' (ID {proj_id})")
    return proj_id

def setup_mirror(project_id, name, owner):
    """
    Configure GitLab pull mirror for the given project.
    GitLab will periodically pull from GitHub.
    """
    url = f"{API_GL}/projects/{project_id}/remote_mirrors"
    payload = {
        "url":                      f"https://oauth2:{GITHUB_TOKEN}"
                                    f"@github.com/{owner}/{name}.git",
        "enabled":                  True,
        "only_protected_branches":  False,
        "keep_divergent_refs":      True
    }
    resp = requests.post(url, headers=gl_headers, data=payload)
    resp.raise_for_status()
    print(f"[INFO] Mirror configured for {owner}/{name}")

def main():
    # Fetch all relevant repos
    repos = fetch_repos()
    print(f"[INFO] Found {len(repos)} repositories to mirror")

    for owner, name in repos:
        # Skip hidden repos (like .github)
        if name.startswith("."):
            continue

        try:
            # Create project if needed and configure mirror
            project_id = create_project(name, owner)
            setup_mirror(project_id, name, owner)
        except Exception as e:
            print(f"[ERROR] {owner}/{name}: {e}")

        # Avoid hitting API rate limits
        time.sleep(1)

if __name__ == "__main__":
    main()
