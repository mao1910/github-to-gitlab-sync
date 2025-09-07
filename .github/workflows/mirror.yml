name: Mirror to GitLab
on:
  schedule:
    - cron: '0 2 * * *'
  workflow_dispatch:

jobs:
  mirror:
    runs-on: ubuntu-latest
    # Extend job timeout to handle large repos (720 minutes = 12 hours)
    timeout-minutes: 720
    env:
      GITHUB_TOKEN: ${{ secrets.GH_PAT }}         # GitHub PAT (repo scope)
      GITLAB_TOKEN: ${{ secrets.GITLAB_TOKEN }}   # GitLab PAT (api + write_repository)
      GITLAB_GROUP_ID: ${{ secrets.GITLAB_GROUP_ID }}
      GITLAB_GROUP_PATH: my-group                 # GitLab namespace path (not ID)
      GITHUB_USER: "mao1910,le-fork"
      GIT_CURL_VERBOSE: "1"                       # Enable libcurl verbose logging
      GIT_TRACE: "1"                              # Enable Git trace output

    steps:
      - name: Checkout this workflow
        uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.x'

      - name: Install dependencies
        run: |
          pip install --upgrade pip
          pip install requests

      - name: Create GitLab projects
        run: python mirror_repos.py

      - name: Mirror via push
        shell: bash
        run: |
          # Configure Git identity for pushes
          git config --global user.name "GitHub Actions"
          git config --global user.email "actions@github.com"

          # Increase HTTP buffer and slow-speed settings to prevent timeouts
          git config --global http.postBuffer 524288000     # 500 MB
          git config --global http.lowSpeedLimit 1000
          git config --global http.lowSpeedTime 300

          # Ensure we fetch all branches and tags only
          git config --global remote.origin.fetch "+refs/heads/*:refs/heads/*"
          git config --global --add remote.origin.fetch "+refs/tags/*:refs/tags/*"

          failed=()
          success=()

          IFS=',' read -ra USERS <<< "$GITHUB_USER"
          for user in "${USERS[@]}"; do
            user="${user//[[:space:]]/}"
            echo "=== Processing user: $user ==="

            # Fetch repository list
            repos=$(curl -s -H "Authorization: token $GITHUB_TOKEN" \
              "https://api.github.com/users/$user/repos?per_page=100&type=all" | \
              jq -r '.[].name')

            for repo in $repos; do
              if [[ "$repo" == .* ]]; then
                echo "Skipping hidden repo: $user/$repo"
                continue
              fi

              echo "Cloning $user/$repo …"
              if ! timeout 3600 git clone --mirror \
                  "https://oauth2:${GITHUB_TOKEN}@github.com/${user}/${repo}.git"; then
                echo "❌ Clone failed: $user/$repo"
                failed+=("$user/$repo")
                continue
              fi

              cd "${repo}.git"

              # Strip any extraneous refs that could cause conflicts
              git config remote.origin.fetch "+refs/heads/*:refs/heads/*"
              git config --add remote.origin.fetch "+refs/tags/*:refs/tags/*"

              echo "Pushing $user/$repo → GitLab group/${repo}"
              if ! timeout 3600 git push --force --mirror \
                  "https://oauth2:${GITLAB_TOKEN}@gitlab.com/${GITLAB_GROUP_PATH}/${repo}.git"; then
                echo "❌ Push failed: $user/$repo"
                failed+=("$user/$repo")
              else
                echo "✅ Success: $user/$repo"
                success+=("$user/$repo")
              fi

              cd ..
              rm -rf "${repo}.git"

              # Delay to avoid API rate limits
              sleep 10
            done
          done

          echo "=== SUMMARY ==="
          echo "Succeeded: ${#success[@]}"
          echo "Failed:    ${#failed[@]}"
          if [ ${#failed[@]} -gt 0 ]; then
            echo "Failed repositories:"
            printf '%s\n' "${failed[@]}"
            exit 1
          fi
