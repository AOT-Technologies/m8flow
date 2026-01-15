# Workflow Configuration Guide

## Overview

These workflows sync changes from an upstream repository, selectively merging only backend and frontend changes while ignoring other upstream modifications.

## Upstream Repository

**Default Upstream:** `https://github.com/AOT-Technologies/m8flow.git`

This is the source repository that your fork syncs from. The workflows pull changes from this repository and selectively apply only changes to:
- `spiffworkflow-backend/`
- `spiffworkflow-frontend/`

All other upstream changes (root files, `.github/`, `docs/`, etc.) are ignored to maintain your repository's custom structure.

## Required Configuration

### 1. GitHub Secrets

#### Optional: `UPSTREAM_REPO_URL`

**When to configure:**
- If your upstream repository URL is different from the default
- If the upstream repository is private and requires authentication

**How to configure:**
1. Go to **Settings** → **Secrets and variables** → **Actions**
2. Click **New repository secret**
3. Name: `UPSTREAM_REPO_URL`
4. Value: Your upstream repository URL (e.g., `https://github.com/org/repo.git`)

**If not configured:**
- The workflow will use the default: `https://github.com/AOT-Technologies/m8flow.git`
- This works for public repositories

#### Automatic: `GITHUB_TOKEN`

**No configuration needed** - This is automatically provided by GitHub Actions with the required permissions:
- `contents: write` - To create branches and commits
- `pull-requests: write` - To create PRs
- `actions: write` - To trigger other workflows (for check-upstream.yml)

## Workflows

### 1. `check-upstream.yml`

**Purpose:** Periodically checks upstream for changes and automatically triggers sync if changes are detected.

**Triggers:**
- **Scheduled:** Every Monday at midnight UTC (`0 0 * * 1`)
- **Manual:** Can be triggered manually via workflow_dispatch

**What it does:**
1. Fetches the upstream repository
2. Compares current HEAD with upstream
3. Checks for changes in `spiffworkflow-backend/` or `spiffworkflow-frontend/`
4. If changes found → automatically triggers `sync-upstream.yml`

**Configuration:**
- Uses `UPSTREAM_REPO_URL` secret (or default)
- Requires `actions: write` permission (automatically granted via `GITHUB_TOKEN`)

### 2. `sync-upstream.yml`

**Purpose:** Selectively syncs backend/frontend changes from upstream and creates a PR.

**Triggers:**
- **Manual:** Via workflow_dispatch (can be triggered by check-upstream.yml or manually)
- **Input:** `upstream_branch` (default: `main`)

**What it does:**
1. Fetches upstream repository
2. Identifies changed files in backend/frontend directories
3. Creates a new branch
4. Applies only backend/frontend changes
5. Creates a Pull Request with the changes

**Configuration:**
- Uses `UPSTREAM_REPO_URL` secret (or default)
- Requires `contents: write` and `pull-requests: write` permissions (automatically granted)

## Setup Checklist

- [ ] Verify upstream repository URL is correct (default: `https://github.com/AOT-Technologies/m8flow.git`)
- [ ] If using a different upstream URL, add `UPSTREAM_REPO_URL` secret
- [ ] If upstream is private, ensure `GITHUB_TOKEN` has access (usually automatic)
- [ ] Test manual trigger of `sync-upstream.yml` workflow
- [ ] Verify scheduled `check-upstream.yml` runs on Mondays

## Troubleshooting

### Workflow fails with "remote not found" or authentication errors

**Solution:** 
- If upstream is private, ensure the repository has access to the upstream repo
- Check that `UPSTREAM_REPO_URL` secret is set correctly (if using custom URL)

### Workflow runs but finds no changes

**Possible reasons:**
- Upstream is already in sync
- Changes exist but not in `spiffworkflow-backend/` or `spiffworkflow-frontend/` (these are intentionally ignored)
- Wrong branch specified in `upstream_branch` input

### Cannot trigger workflows

**Solution:**
- Ensure workflows are triggered from `main` branch only
- Check that you have write permissions to the repository
- Verify workflow files are in `.github/workflows/` directory
