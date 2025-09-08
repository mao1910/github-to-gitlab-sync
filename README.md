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
   - Namespace path (e.g., `mao191-group`), hard-coded in workflow  

4. **GitHub Usernames**  
   - Comma-separated list (e.g., `mao1910,le-fork`), hard-coded in workflow  

***

## Repository Structure

```text
.
├── .github/
│   └── workflows/
│       └── mirror-to-gitlab.yml   # GitHub Actions workflow
├── mirror_repos.py                # Python script for mirror setup
└── README.md                      # This documentation
```

***

## Configuration

### Secrets

In your GitHub repository’s **Settings → Secrets and variables → Actions**, add:

- `GH_PAT`           – GitHub PAT with `repo` scope  
- `GITLAB_TOKEN`     – GitLab PAT with `api` and `write_repository` scopes  
- `GITLAB_GROUP_ID`  – Numeric ID of your GitLab *group*  

### Workflow Variables

The following values are **hard-coded** in `.github/workflows/mirror-to-gitlab.yml`:

- `GITLAB_GROUP_PATH` – Your GitLab namespace path (e.g., `mao191-group`)  
- `GITHUB_USER`       – Comma-separated GitHub usernames to mirror  

Edit these if you mirror into a different *group* or from different users.

***

## Usage

1. **Push to GitHub**  
   The workflow triggers on schedule (03:00 UTC daily) or manual dispatch.  

2. **Mirror Setup**  
   - The Python script fetches all repos, creates missing GitLab projects, and configures pull mirrors.  
   - On failure or edge cases, the fallback push-mirror clones and pushes any unmatched repos.

3. **Verify in GitLab**  
   Check your GitLab *group* to ensure all expected repositories exist and are updating.

***

## How It Works

1. **fetch_repos()** (in `mirror_repos.py`)  
   - Lists private & owned repos via `GET /user/repos`  
   - Lists public & forked repos via `GET /users/{owner}/repos`  
   - Combines and deduplicates both lists  

2. **create_project(name, owner)**  
   - Searches existing projects under your *group*  
   - If not found, uses numeric `GITLAB_GROUP_ID` to create a new private project  

3. **setup_mirror(project_id, name, owner)**  
   - Configures a **pull mirror** in GitLab pointing to your GitHub repo  

4. **Fallback push step**  
   - Reconstructs combined repo list via GitHub API  
   - Skips dot-prefixed repos (`.github`)  
   - Verifies project exists in GitLab by URL-encoded path  
   - Performs a `git clone --mirror` and `git push --mirror` for each  

***

## Customization

- **Cron schedule**: Edit `cron: '0 3 * * *'` in workflow for different timings.  
- **Visibility**: Change `"private"` to `"public"` in `mirror_repos.py` payload if you prefer public mirrors.  
- **Additional users**: Extend `GITHUB_USER` list to include multiple GitHub accounts.  
- **Rate limits**: The script uses a `time.sleep(1)` between API calls; adjust if needed.  

***

## License

Released under the MIT License. Feel free to fork, modify, and extend to suit your needs.
