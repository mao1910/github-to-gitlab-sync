import os
import requests

# ====== Configuration (from CI/CD variables) ======
GITHUB_TOKEN    = os.environ["GITHUB_TOKEN"]       # GitHub Personal Access Token (with repo scope)
GITHUB_USER     = os.environ["GITHUB_USER"]        # Comma-separated GitHub username(s) or org name(s)
GITLAB_TOKEN    = os.environ["GITLAB_TOKEN"]       # GitLab Personal Access Token (with api scope)
GITLAB_URL      = os.environ.get("GITLAB_URL", "https://gitlab.com")
GITLAB_GROUP_ID = os.environ["GITLAB_GROUP_ID"]    # Numeric ID of the GitLab group/namespace
# ==================================================

gh_headers = {"Authorization": f"token {GITHUB_TOKEN}"}
gl_headers = {"PRIVATE-TOKEN": GITLAB_TOKEN}


def fetch_github_repos(user):
    """
    Fetch all GitHub repositories for a given user or org visible to the PAT.
    """
    repos, page = [], 1
    while True:
        r = requests.get(
            "https://api.github.com/user/repos",
            headers=gh_headers,
            params={
                "per_page": 100,
                "page": page,
                "type": "all"
            }
        )
        r.raise_for_status()
        data = r.json()
        if not data:
            break
        # Filter to only the specified user/org's repos
        for repo in data:
            if repo["owner"]["login"].lower() == user.lower():
                repos.append(repo["name"])
        page += 1
    return repos


def create_gitlab_project(name):
    """
    Create a new GitLab project under the specified group.
    Uses namespace_id to avoid name-based lookup issues.
    """
    url = f"{GITLAB_URL}/api/v4/projects"
    payload = {
        "name": name,
        "namespace_id": GITLAB_GROUP_ID,
        "visibility": "private"
    }
    r = requests.post(url, headers=gl_headers, data=payload)
    r.raise_for_status()
    return r.json()["id"]


def setup_pull_mirror(project_id, repo_name, user):
    """
    Configure a pull mirror for the given GitLab project.
    Uses embedded credentials in the HTTPS URL for authentication.
    """
    url = f"{GITLAB_URL}/api/v4/projects/{project_id}/remote_mirrors"
    payload = {
        "url": f"https://{user}:{GITHUB_TOKEN}@github.com/{user}/{repo_name}.git",
        "enabled": True,
        "only_protected_branches": False,
        "keep_divergent_refs": True
    }
    r = requests.post(url, headers=gl_headers, data=payload)
    r.raise_for_status()


def main():
    # Parse comma-separated users/orgs
    users = [u.strip() for u in GITHUB_USER.split(",") if u.strip()]
    all_repos = []

    # Fetch repos for each user/org
    for user in users:
        repos = fetch_github_repos(user)
        print(f"Found {len(repos)} repositories for '{user}'.")
        for name in repos:
            all_repos.append((user, name))

    # Iterate and mirror each repo
    for user, name in all_repos:
        print(f"Mirroring '{user}/{name}'…", end=" ")
        try:
            proj_id = create_gitlab_project(name)
            setup_pull_mirror(proj_id, name, user)
            print("Done.")
        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    main()
