# github-to-gitlab-sync

Automate one-way mirroring of **all** GitHub repositories (private, owned, public, forks) to a GitLab *group*.  
Keeps your full commit history and contribution graphs in sync across both platforms using only GitHub Actions.

***

## Features

- Fetches every repository visible to your GitHub PAT  
- Creates or updates a **private** project in a specified GitLab *group*  
- Configures **GitLab pull mirrors** for automatic upstream updates, with a **push-mirror fallback** to handle any edge cases  
- Fallback push-mirror step to catch any repos not covered by the pull configuration  
- Safe, auditable setup with minimal manual steps  
- **Prune job** to automatically identify and remove projects deleted on GitHub after a configurable grace period, with dry-run support  

***

## Prerequisites

1. **GitHub Personal Access Token**  
   - Scope: `repo`  
   - Stored in GitHub Actions as secret `GH_PAT`  

2. **GitLab Personal Access Token**  
   - Scopes: `api`, `write_repository`  
   - Stored as secret `GITLAB_TOKEN`  

3. **GitLab Group**  
   - Numeric group ID, stored as secret `GITLAB_GROUP_ID`  
   - Namespace path (e.g., `mao1910-group`), hard-coded in workflows  

4. **GitHub Usernames**  
   - Comma-separated list (e.g., `mao1910,le-fork`), hard-coded in workflows  

5. *(Optional)* **PRUNE_EXCLUDE**  
   - Comma-separated project names to never delete (defaults to `mirror-scripts`)  

***

## Repository Structure

```text
.
├── .github/
│   └── workflows/
│       ├── mirror-to-gitlab.yml   # Mirror setup workflow
│       └── prune-stale.yml        # Prune stale projects workflow
├── sync_repos.py                  # Python script for mirror setup
├── cleanup_pruned_repos.py        # Python script for pruning stale projects
└── README.md                      # This documentation
```

***

## Configuration

### Secrets & Variables

In **Settings → Secrets and variables → Actions**, add:

- `GH_PAT`           – GitHub PAT with `repo` scope  
- `GITLAB_TOKEN`     – GitLab PAT with `api` and `write_repository` scopes  
- `GITLAB_GROUP_ID`  – Numeric ID of your GitLab *group*  
- `PRUNE_EXCLUDE`    – *(Optional)* Projects to always keep during prune  

Hard-coded in the workflows:

- `GITHUB_USER`      – Comma-separated GitHub usernames (mirror source)  
- `GITLAB_GROUP_PATH` – GitLab namespace path (mirror target)  

***

## Usage

### 1. Mirroring

- The **mirror-to-gitlab.yml** workflow runs on schedule (daily at 03:00 UTC by default) or manual dispatch.
- It installs dependencies, runs `sync_repos.py`, and ensures each GitHub repo exists in GitLab with pull-mirror + fallback push-mirror.

### 2. Pruning Stale Projects

- The **prune-stale.yml** workflow runs weekly (Sunday at 03:00 UTC by default) or manual dispatch.
- It restores `prune_state.json`, runs `cleanup_pruned_repos.py` in **dry-run** mode by default, and updates the cache.

#### Checking Dry-Run Output

1. In the workflow run, expand the **Dry-run prune** step.
2. Look for lines like:
   ```
   [DRY RUN] Would delete 'obsolete-repo' (project ID 123456)
   ```
   These are projects no longer on GitHub and past the grace period.

#### Activating Actual Deletion

1. After verifying dry-run candidates, edit **prune-stale.yml**:
   ```yaml
   DRY_RUN: "false"
   ```
2. Commit and rerun the workflow.  
3. The logs will show:
   ```
   Deleting 'obsolete-repo' (project ID 123456)… Done.
   ```
4. **Safety Tip:** Revert `DRY_RUN` back to `"true"` after pruning to prevent unintended deletions.

***

## How It Works

### sync_repos.py

1. **fetch_repos()**  
   - Lists private & owned repos via `GET /user/repos`  
   - Lists public & forked repos via `GET /users/{owner}/repos` for each `GITHUB_USER`  
   - Combines and deduplicates  

2. **create_project(name, owner)**  
   - Searches existing projects under your *group*  
   - Creates a new private project if missing  

3. **setup_mirror(project_id, name, owner)**  
   - Configures a **pull mirror** in GitLab  
   - Falls back to `git clone --mirror` + `git push --mirror` for edge cases  

### cleanup_pruned_repos.py

1. **fetch_github_repos()**  
   - Same dual-fetch logic as mirror script  

2. **list_gitlab_projects()**  
   - Retrieves all projects in your GitLab group  

3. **State Tracking**  
   - Uses `prune_state.json` to record last-seen timestamps  

4. **Prune Logic**  
   - Projects missing on GitHub are marked with a timestamp  
   - Only deleted after `GRACE_DAYS` have passed  
   - Respects `PRUNE_EXCLUDE` to protect utility repos  

5. **Dry-Run vs. Delete**  
   - `DRY_RUN=true` lists candidates only  
   - `DRY_RUN=false` issues `DELETE /projects/:id` for each  

***

## Customization

- **Cron schedules:** Adjust `cron` entries in workflows.  
- **Grace period:** Change `GRACE_DAYS` in prune workflow env.  
- **Exclusions:** Update `PRUNE_EXCLUDE` to protect essential projects.  
- **Visibility:** Modify payload in `sync_repos.py` to create public mirrors.  
- **Rate limiting:** Tweak `time.sleep(1)` in mirror script as needed.  

***

## License

Released under the MIT License. Feel free to fork, modify, and extend to suit your needs.
