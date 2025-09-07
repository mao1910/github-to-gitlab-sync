#!/usr/bin/env python3
import os
import requests
import time
import sys

# ====== Configuration ======
GITHUB_TOKEN      = os.environ["GITHUB_TOKEN"]       # Your GH_PAT (repo scope)
GITHUB_USER       = os.environ["GITHUB_USER"]        # Comma-separated GitHub usernames/orgs
GITLAB_TOKEN      = os.environ["GITLAB_TOKEN"]       # GitLab PAT (api+write_repository)
GITLAB_URL        = os.environ.get("GITLAB_URL", "https://gitlab.com")
GITLAB_GROUP_PATH = os.environ["GITLAB_GROUP_PATH"]  # e.g. "mao191-group"
# ===========================

gh_headers = {"Authorization": f"token {GITHUB_TOKEN}"}
gl_headers = {"PRIVATE-TOKEN": GITLAB_TOKEN}

def fetch_github_repos():
    """
    Fetch all repos accessible to the authenticated user (private & owned)
    and all public repos under the first GITHUB_USER entry (including forks).
    """
    owner = GITHUB_USER.split(",")[0].strip()
    repos = []
    page = 1

    while True:
        # 1) Private & owned repos
        resp1 = requests.get(
            "https://api.github.com/user/repos",
            headers=gh_headers,
            params={"per_page": 100, "page": page, "type": "all", "sort": "updated"}
        )
        resp1.raise_for_status()
        data1 = resp1.json()

        # 2) All public repos under the username (including forks)
        resp2 = requests.get(
            f"https://api.github.com/users/{owner}/repos",
            headers=gh_headers,
            params={"per_page": 100, "page": page, "type": "all", "sort": "updated"}
        )
        resp2.raise_for_status()
        data2 = resp2.json()

        combined = {repo["full_name"]: repo for repo in (data1 + data2)}.values()
        if not combined:
            break

        for repo in combined:
            repos.append({"owner": repo["owner"]["login"], "name": repo["name"]})

        page += 1

    return repos

def get_existing_project_id(name):
    url = f"{GITLAB_URL}/api/v4/groups/{GITLAB_GROUP_PATH}/projects"
    resp = requests.get(url, headers=gl_headers, params={"search": name})
    resp.raise_for_status()
    for proj in resp.json():
        if proj["name"].lower() == name.lower():
            return proj["id"]
    return None

def create_gitlab_project(name, description=None):
    existing = get_existing_project_id(name)
    if existing:
        print(f"[INFO] Project '{name}' exists (ID {existing})")
        return existing

    # Fetch numeric group ID
    grp = requests.get(f"{GITLAB_URL}/api/v4/groups/{GITLAB_GROUP_PATH}", headers=gl_headers)
    grp.raise_for_status()
    group_id = grp.json()["id"]

    payload = {
        "name": name,
        "namespace_id": group_id,
        "visibility": "private",
        "description": description or f"Mirror of https://github.com/{name}"
    }
    resp = requests.post(f"{GITLAB_URL}/api/v4/projects", headers=gl_headers, data=payload)
    resp.raise_for_status()
    pid = resp.json()["id"]
    print(f"[INFO] Created '{name}' (ID {pid})")
    return pid

def setup_pull_mirror(pid, repo_name, owner):
    url = f"{GITLAB_URL}/api/v4/projects/{pid}/remote_mirrors"
    payload = {
        "url": f"https://oauth2:{GITHUB_TOKEN}@github.com/{owner}/{repo_name}.git",
        "enabled": True,
        "only_protected_branches": False,
        "keep_divergent_refs": True
    }
    resp = requests.post(url, headers=gl_headers, data=payload)
    resp.raise_for_status()
    print(f"[INFO] Mirror configured for {owner}/{repo_name}")

def main():
    if not (GITHUB_TOKEN and GITLAB_TOKEN and GITLAB_GROUP_PATH and GITHUB_USER):
        print("[ERROR] Missing required environment variables.")
        sys.exit(1)

    repos = fetch_github_repos()
    print(f"[INFO] Found {len(repos)} repos to mirror")
    for r in repos:
        owner, name = r["owner"], r["name"]
        if name.startswith("."):
            continue
        try:
            pid = create_gitlab_project(name, description=f"Mirror of https://github.com/{owner}/{name}")
            setup_pull_mirror(pid, name, owner)
        except Exception as e:
            print(f"[ERROR] {owner}/{name}: {e}")
        time.sleep(1)

if __name__ == "__main__":
    main()
