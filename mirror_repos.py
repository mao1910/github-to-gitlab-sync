import os
import requests

# ====== Configuration (from CI/CD variables) ======
GITHUB_TOKEN    = os.environ["GITHUB_TOKEN"]       # GitHub PAT (repo scope)
GITHUB_USER     = os.environ["GITHUB_USER"]        # Comma-separated GitHub usernames/orgs
GITLAB_TOKEN    = os.environ["GITLAB_TOKEN"]       # GitLab PAT (api scope)
GITLAB_URL      = os.environ.get("GITLAB_URL", "https://gitlab.com")
GITLAB_GROUP_ID = os.environ["GITLAB_GROUP_ID"]    # Numeric GitLab group ID
# ==================================================

gh_headers = {"Authorization": f"token {GITHUB_TOKEN}"}
gl_headers = {"PRIVATE-TOKEN": GITLAB_TOKEN}

def fetch_github_repos(user):
    repos, page = [], 1
    while True:
        r = requests.get(
            "https://api.github.com/user/repos",
            headers=gh_headers,
            params={"per_page": 100, "page": page, "type": "all"}
        )
        r.raise_for_status()
        data = r.json()
        if not data:
            break
        for repo in data:
            if repo["owner"]["login"].lower() == user.lower():
                repos.append(repo["name"])
        page += 1
    return repos

def get_existing_project_id(name):
    """
    If a project with this name exists in the group, return its ID.
    """
    url = f"{GITLAB_URL}/api/v4/groups/{GITLAB_GROUP_ID}/projects"
    params = {"search": name}
    r = requests.get(url, headers=gl_headers, params=params)
    r.raise_for_status()
    for proj in r.json():
        if proj["name"].lower() == name.lower():
            return proj["id"]
    return None

def create_gitlab_project(name):
    """
    Create a new GitLab project under the specified group,
    or return the ID of an existing project if already created.
    """
    url = f"{GITLAB_URL}/api/v4/projects"
    payload = {
        "name": name,
        "namespace_id": GITLAB_GROUP_ID,
        "visibility": "private"
    }
    r = requests.post(url, headers=gl_headers, data=payload)
    if r.status_code == 400:
        msg = r.json().get("message", {})
        # If project already exists, fetch its ID
        if any("has already been taken" in errs for errs in msg.values()):
            existing_id = get_existing_project_id(name)
            if existing_id:
                print(f"[INFO] Project '{name}' already exists with ID {existing_id}.")
                return existing_id
        # Otherwise raise
        print(f"[ERROR] Creating project '{name}': {r.status_code} {r.text}")
        r.raise_for_status()
    r.raise_for_status()
    proj_id = r.json()["id"]
    print(f"[INFO] Created project '{name}' with ID {proj_id}.")
    return proj_id


def setup_pull_mirror(project_id, repo_name, user):
    url = f"{GITLAB_URL}/api/v4/projects/{project_id}/remote_mirrors"
    payload = {
        "url": f"https://oauth2:{GITHUB_TOKEN}@github.com/{user}/{repo_name}.git",
        "enabled": True,
        "only_protected_branches": False,
        "keep_divergent_refs": True
    }
    r = requests.post(url, headers=gl_headers, data=payload)
    r.raise_for_status()
}

def main():
    users = [u.strip() for u in GITHUB_USER.split(",") if u.strip()]
    all_repos = []
    for user in users:
        repos = fetch_github_repos(user)
        print(f"Found {len(repos)} repositories for '{user}'.")
        for name in repos:
            all_repos.append((user, name))

    for user, name in all_repos:
        if name.startswith("."):
            print(f"Skipping hidden repo '{user}/{name}'")
            continue
            
        print(f"Mirroring '{user}/{name}'…", end=" ")
        try:
            proj_id = create_gitlab_project(name)
            setup_pull_mirror(proj_id, name, user)
            print("Done.")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    main()
