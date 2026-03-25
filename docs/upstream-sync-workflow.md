# Upstream Sync Workflow

The `sync-upstream.yml` workflow selectively syncs changes from upstream that only affect:
- `spiffworkflow-backend/`
- `spiffworkflow-frontend/`

All other upstream changes (root files, `.github/`, `docs/`, etc.) are ignored to maintain your repository restructure.

## How to Use

1. Go to the **Actions** tab in your GitHub repository
2. Select **"Sync Upstream Changes"** from the workflow list
3. Click **"Run workflow"**
4. Select the branch (default: `main`) and upstream branch to sync from (default: `main`)
5. Click **"Run workflow"**

The workflow will:
- Fetch changes from upstream
- Check for changes in backend/frontend directories only
- Create a new branch with the changes
- Open a Pull Request automatically
- Add labels: `upstream-sync` and `automated`

## Configuration

### Required Secrets

If your upstream repository URL is different from the default, add a secret:

1. Go to **Settings** → **Secrets and variables** → **Actions**
2. Add a new repository secret:
   - **Name**: `UPSTREAM_REPO_URL`
   - **Value**: Your upstream repository URL (e.g., `https://github.com/AOT-Technologies/m8flow.git`)

If not set, it defaults to `https://github.com/AOT-Technologies/m8flow.git`

### Permissions

The workflow requires:
- `contents: write` - To create branches and commits
- `pull-requests: write` - To create PRs

These are automatically granted via `GITHUB_TOKEN`.

## What Gets Synced

✅ **Included:**
- Any changes to files in `spiffworkflow-backend/`
- Any changes to files in `spiffworkflow-frontend/`

❌ **Excluded:**
- Root-level files (README.md, docker-compose.yml, etc.)
- `.github/` directory changes
- `docs/` directory changes
- Any other directories outside backend/frontend

## Review Process

After the workflow runs:
1. Review the created PR
2. Check the file changes carefully
3. Run tests if needed
4. Merge when ready

The PR will be automatically labeled and can be reviewed like any other PR.
