import os
import requests
import json
from datetime import datetime, timedelta

# ====== Configuration (from CI/CD variables) ======
GITHUB_TOKEN    = os.environ["GITHUB_TOKEN"]
GITLAB_TOKEN    = os.environ["GITLAB_TOKEN"]
GITLAB_URL      = os.environ.get("GITLAB_URL", "https://gitlab.com")
GITLAB_GROUP_ID = os.environ["GITLAB_GROUP_ID"]
DRY_RUN         = os.environ.get("DRY_RUN", "true").lower() == "true"
GRACE_DAYS      = int(os.environ.get("GRACE_DAYS", "7"))
# Comma-separated list of project names to never delete
EXCLUDE         = set(os.environ.get("PRUNE_EXCLUDE", "mirror-scripts").split(","))
# ==================================================

gl_headers = {"PRIVATE-TOKEN": GITLAB_TOKEN}
STATE_FILE = "prune_state.json"

def list_gitlab_projects():
    """Return dict name → project ID."""
    projects, page = {}, 1
    while True:
        r = requests.get(
            f"{GITLAB_URL}/api/v4/groups/{GITLAB_GROUP_ID}/projects",
            headers=gl_headers,
            params={"per_page": 100, "page": page}
        )
        r.raise_for_status()
        data = r.json()
        if not data:
            break
        for p in data:
            projects[p["name"]] = p["id"]
        page += 1
    return projects

def fetch_github_repos():
    """List all GitHub repo names visible to the PAT (personal + org)."""
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    repos, page = [], 1
    while True:
        r = requests.get(
            "https://api.github.com/user/repos",
            headers=headers,
            params={"per_page": 100, "page": page, "type": "all"}
        )
        r.raise_for_status()
        data = r.json()
        if not data:
            break
        repos.extend([repo["name"] for repo in data])
        page += 1
    return set(repos)

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

    # Update last-seen timestamps for existing repos
    for name in gl_projects:
        if name in gh_names or name in EXCLUDE:
            state[name] = now.isoformat()

    to_delete = []
    for name, proj_id in gl_projects.items():
        if name in EXCLUDE or name in gh_names:
            continue
        last_seen = state.get(name)
        if last_seen:
            delta = now - datetime.fromisoformat(last_seen)
            if delta >= timedelta(days=GRACE_DAYS):
                to_delete.append((name, proj_id))
        else:
            # First time missing: record timestamp
            state[name] = now.isoformat()

    save_state(state)

    # Report or perform deletions
    for name, proj_id in to_delete:
        if DRY_RUN:
            print(f"[DRY RUN] Would delete '{name}' (project ID {proj_id})")
        else:
            print(f"Deleting '{name}' (project ID {proj_id})…", end=" ")
            r = requests.delete(f"{GITLAB_URL}/api/v4/projects/{proj_id}", headers=gl_headers)
            r.raise_for_status()
            print("Done.")

if __name__ == "__main__":
    prune_deleted_repos()
