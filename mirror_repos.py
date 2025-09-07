#!/usr/bin/env python3
import os, requests, time, sys

# Required env vars
GITHUB_TOKEN     = os.getenv("GITHUB_TOKEN")
GITLAB_TOKEN     = os.getenv("GITLAB_TOKEN")
GITLAB_GROUP_ID  = os.getenv("GITLAB_GROUP_ID")   # numeric
GITLAB_GROUP_PATH= os.getenv("GITLAB_GROUP_PATH") # string
GITHUB_USER      = os.getenv("GITHUB_USER")

if not all([GITHUB_TOKEN, GITLAB_TOKEN, GITLAB_GROUP_ID, GITLAB_GROUP_PATH, GITHUB_USER]):
    print("[ERROR] Missing one of: GITHUB_TOKEN, GITLAB_TOKEN, GITLAB_GROUP_ID, GITLAB_GROUP_PATH, GITHUB_USER")
    sys.exit(1)

gh = {"Authorization": f"token {GITHUB_TOKEN}"}
gl = {"PRIVATE-TOKEN": GITLAB_TOKEN}
API = "https://api.github.com"
GL  = "https://gitlab.com/api/v4"

def fetch_repos():
    owner = GITHUB_USER.split(",")[0].strip()
    repos = []
    page = 1
    while True:
        # 1) private & owned
        r1 = requests.get(f"{API}/user/repos", headers=gh,
            params={"per_page":100,"page":page,"type":"all","sort":"updated"})
        r1.raise_for_status()
        # 2) public & forks
        r2 = requests.get(f"{API}/users/{owner}/repos", headers=gh,
            params={"per_page":100,"page":page,"type":"all","sort":"updated"})
        r2.raise_for_status()

        combined = {repo["full_name"]: repo for repo in (r1.json()+r2.json())}.values()
        if not combined:
            break
        for repo in combined:
            repos.append((repo["owner"]["login"], repo["name"]))
        page += 1
    return repos

def get_proj_id(name):
    r = requests.get(f"{GL}/groups/{GITLAB_GROUP_PATH}/projects", headers=gl, params={"search":name})
    r.raise_for_status()
    for p in r.json():
        if p["name"].lower()==name.lower():
            return p["id"]
    return None

def create_project(name, owner):
    pid = get_proj_id(name)
    if pid:
        print(f"[INFO] '{name}' exists (ID {pid})")
        return pid
    payload = {
        "name": name,
        "namespace_id": int(GITLAB_GROUP_ID),
        "visibility": "private",
        "description": f"Mirror of https://github.com/{owner}/{name}"
    }
    r = requests.post(f"{GL}/projects", headers=gl, data=payload)
    r.raise_for_status()
    pid = r.json()["id"]
    print(f"[INFO] Created '{name}' (ID {pid})")
    return pid

def setup_mirror(pid, name, owner):
    url = f"{GL}/projects/{pid}/remote_mirrors"
    data = {
        "url": f"https://oauth2:{GITHUB_TOKEN}@github.com/{owner}/{name}.git",
        "enabled": True,
        "only_protected_branches": False,
        "keep_divergent_refs": True
    }
    r = requests.post(url, headers=gl, data=data)
    r.raise_for_status()
    print(f"[INFO] Mirror configured for {owner}/{name}")

def main():
    repos = fetch_repos()
    print(f"[INFO] Found {len(repos)} repos")
    for owner, name in repos:
        if name.startswith("."): continue
        try:
            pid = create_project(name, owner)
            setup_mirror(pid, name, owner)
        except Exception as e:
            print(f"[ERROR] {owner}/{name}: {e}")
        time.sleep(1)

if __name__=="__main__":
    main()
