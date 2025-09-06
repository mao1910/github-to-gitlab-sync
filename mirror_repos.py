import os
import requests

# ====== Configuration (from CI/CD variables) ======
GITHUB_TOKEN    = os.environ["GITHUB_TOKEN"]       # GitHub Personal Access Token (with repo scope)
GITHUB_USER     = os.environ["GITHUB_USER"]        # GitHub username or org name
GITLAB_TOKEN    = os.environ["GITLAB_TOKEN"]       # GitLab Personal Access Token (with api scope)
GITLAB_URL      = os.environ.get("GITLAB_URL", "https://gitlab.com")
GITLAB_GROUP_ID = os.environ["GITLAB_GROUP_ID"]    # Numeric ID of the GitLab group/namespace
# ==================================================

gh_headers = {"Authorization": f"token {GITHUB_TOKEN}"}
gl_headers = {"PRIVATE-TOKEN": GITLAB_TOKEN}

def fetch_github_repos():
    """
    Fetch all GitHub repositories visible to the PAT.
    
    params:
      type=all    → includes personal, private, and org repos you have access to
      type=owner  → only repos you personally own (excludes org repos)
    """
    repos, page = [], 1
    while True:
        r = requests.get(
            "https://api.github.com/user/repos",
            headers=gh_headers,
            params={
                "per_page": 100,
                "page": page,
                "type": "owner"      # change to "all" to include organization repos
            }
        )
        r.raise_for_status()
        data = r.json()
        if not data:
            break
        repos.extend(data)
        page += 1
    # Return only the repository names for mirroring
    return [repo["name"] for repo in repos]

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

def setup_pull_mirror(project_id, repo_name):
    """
    Configure a pull mirror for the given GitLab project.
    Uses embedded credentials in the HTTPS URL for authentication.
    """
    url = f"{GITLAB_URL}/api/v4/projects/{project_id}/remote_mirrors"
    payload = {
        "url": f"https://{GITHUB_USER}:{GITHUB_TOKEN}@github.com/{GITHUB_USER}/{repo_name}.git",
        "enabled": True,
        "only_protected_branches": False,
        "keep_divergent_refs": True
    }
    r = requests.post(url, headers=gl_headers, data=payload)
    r.raise_for_status()

def main():
    # Fetch the list of repo names to mirror
    repos = fetch_github_repos()
    print(f"Found {len(repos)} repositories to mirror.")
    
    # Iterate and mirror each repo
    for name in repos:
        print(f"Mirroring '{name}'…", end=" ")
        try:
            proj_id = create_gitlab_project(name)
            setup_pull_mirror(proj_id, name)
            print("Done.")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    main()
