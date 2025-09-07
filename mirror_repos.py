#!/usr/bin/env python3
import os
import requests
import time
import sys

# ====== Configuration (from CI/CD variables) ======
GITHUB_TOKEN    = os.environ.get("GITHUB_TOKEN")    # GitHub PAT (repo scope)
GITHUB_USER     = os.environ.get("GITHUB_USER")     # Comma-separated GitHub usernames/orgs
GITLAB_TOKEN    = os.environ.get("GITLAB_TOKEN")    # GitLab PAT (api + write_repository)
GITLAB_URL      = os.environ.get("GITLAB_URL", "https://gitlab.com")
GITLAB_GROUP_PATH = os.environ.get("GITLAB_GROUP_PATH")  # GitLab group path, e.g. "mao191-group"
# ==================================================

gh_headers = {"Authorization": f"token {GITHUB_TOKEN}"}
gl_headers = {"PRIVATE-TOKEN": GITLAB_TOKEN}

def fetch_github_repos(user):
    repos = []
    page = 1
    while True:
        url = f"https://api.github.com/users/{user}/repos"
        resp = requests.get(
            url,
            headers=gh_headers,
            params={"per_page": 100, "page": page, "type": "all"}
        )
        resp.raise_for_status()
        data = resp.json()
        if not data:
            break
        for repo in data:
            if repo["owner"]["login"].lower() == user.lower():
                repos.append({
                    "name": repo["name"],
                    "updated_at": repo["updated_at"],
                })
        page += 1
    return repos

def get_existing_project_id(name):
    """
    Return GitLab project ID by searching projects under group path.
    """
    # List first 100 projects under group path with search filter
    url = f"{GITLAB_URL}/api/v4/groups/{GITLAB_GROUP_PATH}/projects"
    params = {"search": name, "per_page": 100}
    resp = requests.get(url, headers=gl_headers, params=params)
    resp.raise_for_status()
    for proj in resp.json():
        if proj["name"].lower() == name.lower():
            return proj["id"]
    return None

def create_gitlab_project(name, description=None):
    """
    Create a new GitLab project under the group path or return existing ID.
    """
    existing_id = get_existing_project_id(name)
    if existing_id:
        print(f"[INFO] Project '{name}' already exists with ID {existing_id}")
        return existing_id

    payload = {
        "name": name,
        "namespace_id": None,  # We'll set namespace via path in API URL instead
        "path": name,
        "visibility": "private",
        "description": description or f"Mirror of https://github.com/{name}",
    }
    # Create project with namespace path in URL
    url = f"{GITLAB_URL}/api/v4/projects"
    # Use 'namespace_path' query param to specify group path
    params = {"namespace_id": None}  # We'll remove to avoid confusion
    # Actually GitLab API requires namespace_id (numeric) to create a project.
    # So we must first get the group numeric id from group path.

    # Get numeric group id from path
    group_url = f"{GITLAB_URL}/api/v4/groups/{GITLAB_GROUP_PATH}"
    group_resp = requests.get(group_url, headers=gl_headers)
    group_resp.raise_for_status()
    group_json = group_resp.json()
    numeric_group_id = group_json["id"]
    payload["namespace_id"] = numeric_group_id

    # Post project creation
    resp = requests.post(url, headers=gl_headers, data=payload)
    if resp.status_code == 400:
        msg = resp.json().get("message", {})
        if any("has already been taken" in str(vals) for vals in msg.values()):
            fallback_id = get_existing_project_id(name)
            if fallback_id:
                print(f"[INFO] Conflict resolved: using existing ID {fallback_id}")
                return fallback_id
    resp.raise_for_status()
    proj_id = resp.json()["id"]
    print(f"[INFO] Created project '{name}' with ID {proj_id}")
    return proj_id

def setup_pull_mirror(project_id, repo_name, user):
    """
    Configure GitLab pull mirror from GitHub repo.
    """
    url = f"{GITLAB_URL}/api/v4/projects/{project_id}/remote_mirrors"
    payload = {
        "url": f"https://oauth2:{GITHUB_TOKEN}@github.com/{user}/{repo_name}.git",
        "enabled": True,
        "only_protected_branches": False,
        "keep_divergent_refs": True
    }
    resp = requests.post(url, headers=gl_headers, data=payload)
    resp.raise_for_status()
    print(f"[INFO] Mirror configured for {user}/{repo_name}")

def main():
    if not (GITHUB_TOKEN and GITHUB_USER and GITLAB_TOKEN and GITLAB_GROUP_PATH):
        print("[ERROR] Missing required environment variables.")
        sys.exit(1)

    users = [u.strip() for u in GITHUB_USER.split(",") if u.strip()]
    all_repos = []

    for user in users:
        print(f"[INFO] Fetching repos for '{user}'")
        repos = fetch_github_repos(user)
        print(f"[INFO] Found {len(repos)} repos for '{user}'")
        repos.sort(key=lambda r: r["updated_at"], reverse=True)
        for r in repos:
            all_repos.append((user, r["name"]))

    for user, name in all_repos:
        if name.startswith("."):
            print(f"[INFO] Skipping hidden repo '{user}/{name}'")
            continue
        print(f"[INFO] Processing '{user}/{name}' …", end=" ")
        try:
            proj_id = create_gitlab_project(name, description=f"Mirror of https://github.com/{user}/{name}")
            setup_pull_mirror(proj_id, name, user)
            print("Done")
        except Exception as e:
            print(f"Error: {e}")
        time.sleep(2)

if __name__ == "__main__":
    main()
