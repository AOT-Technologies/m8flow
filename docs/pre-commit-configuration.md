# Pre-Commit Configuration

The `.pre-commit-config.yaml` file configures [pre-commit](https://pre-commit.com/) hooks that automatically run code quality checks and fixes before you commit changes to the repository.

## What is Pre-Commit?

Pre-commit is a framework for managing and maintaining multi-language pre-commit hooks. It runs checks and fixes on your code automatically when you try to commit, ensuring code quality and consistency across the project.

## How It Works

When you run `git commit`, pre-commit automatically:
1. Runs configured hooks on files you're committing
2. Fixes issues automatically when possible (formatting, whitespace, etc.)
3. Blocks the commit if there are unfixable issues (syntax errors, large files, etc.)
4. Shows you what was fixed or what needs attention

## Configured Hooks

The current configuration applies hooks **only to files in `spiffworkflow-backend/`**. Here's what each hook does:

### 1. **check-added-large-files**
- **Purpose**: Prevents accidentally committing large files (>500KB by default)
- **When**: Before commit
- **Action**: Blocks commit if large files are detected

### 2. **check-toml**
- **Purpose**: Validates TOML file syntax
- **When**: Before commit
- **Action**: Blocks commit if TOML files have syntax errors

### 3. **check-yaml**
- **Purpose**: Validates YAML file syntax
- **When**: Before commit
- **Action**: Blocks commit if YAML files have syntax errors

### 4. **end-of-file-fixer**
- **Purpose**: Ensures files end with a newline character
- **When**: Before commit, before push, and manually
- **Action**: Automatically adds newline if missing
- **Scope**: All text files

### 5. **ruff-check**
- **Purpose**: Python linter that checks for code quality issues
- **When**: Before commit
- **Action**: Automatically fixes issues where possible, reports others
- **Exclusions**: 
  - `/migrations/` directory
  - `bin/load_test_message_start_event.py`
- **Note**: Uses `ruff check --fix` to auto-fix issues

### 6. **ruff-format**
- **Purpose**: Python code formatter (replaces Black)
- **When**: Before commit
- **Action**: Automatically formats Python code to consistent style
- **Exclusions**: `/migrations/` directory
- **Note**: Uses `ruff format` for formatting

### 7. **trailing-whitespace**
- **Purpose**: Removes trailing whitespace from lines
- **When**: Before commit, before push, and manually
- **Action**: Automatically removes trailing whitespace
- **Exclusions**: `/migrations/` directory
- **Scope**: All text files

## Setup

### Initial Installation

If you haven't set up pre-commit yet:

```bash
# Install pre-commit (if not already installed)
uv sync  # This installs pre-commit as a dev dependency

# Install the git hooks
uv run pre-commit install
```

This installs the hooks into your `.git/hooks/` directory, so they run automatically on every commit.

### Install for Pre-Push Hooks

Some hooks also run before push. To enable those:

```bash
uv run pre-commit install --hook-type pre-push
```

## Usage

### Automatic (Recommended)

Once installed, hooks run automatically when you commit:

```bash
git add .
git commit -m "Your commit message"
# Hooks run automatically here
```

If hooks make changes, you'll need to add them and commit again:

```bash
git add .  # Add the fixes made by hooks
git commit -m "Your commit message"  # Commit again
```

### Manual Execution

You can run hooks manually on all files or specific files:

```bash
# Run on all files
uv run pre-commit run --all-files

# Run on specific files
uv run pre-commit run --files spiffworkflow-backend/src/myfile.py

# Run a specific hook
uv run pre-commit run ruff-check --all-files
```

### Running in CI

The repository includes a script for running pre-commit in CI environments:

```bash
./bin/run_pre_commit_in_ci
```

This is used by GitHub Actions workflows to ensure code quality before merging.

## Integration with Other Tools

### `bin/run_pyl`

The `./bin/run_pyl` script runs pre-commit as part of a larger test suite:

```bash
./bin/run_pyl
```

This runs:
1. Pre-commit hooks on backend files
2. Frontend linting (npm)
3. Python type checking (mypy)
4. Python unit tests

### CI/CD

Pre-commit is also run in CI/CD pipelines to catch issues before code is merged.

## Bypassing Hooks (Not Recommended)

If you absolutely need to bypass hooks (not recommended):

```bash
git commit --no-verify -m "Your message"
```

⚠️ **Warning**: Only bypass hooks if you understand the consequences. The hooks are there to maintain code quality.

## Configuration Details

### File Scope

All hooks are configured to only run on files in `spiffworkflow-backend/`:

```yaml
files: ^spiffworkflow-backend/
```

This means:
- ✅ Files in `spiffworkflow-backend/` are checked
- ❌ Files in `spiffworkflow-frontend/` are not checked (uses npm/eslint instead)
- ❌ Root-level files are not checked

### Exclusions

Some hooks exclude certain files/directories:
- **Migrations**: `/migrations/` directory is excluded from formatting/linting
- **Test files**: `bin/load_test_message_start_event.py` is excluded from ruff-check

### Hook Stages

Hooks can run at different stages:
- **pre-commit**: Runs when you commit (default)
- **pre-push**: Runs when you push (requires `pre-commit install --hook-type pre-push`)
- **manual**: Can be run manually with `pre-commit run`

## Troubleshooting

### Hooks Not Running

If hooks aren't running automatically:

```bash
# Reinstall hooks
uv run pre-commit uninstall
uv run pre-commit install
```

### Hook Fails but You Need to Commit

1. **Fix the issues**: Most hooks auto-fix issues. Run `git add .` and commit again.
2. **Check the output**: Read the error message to understand what needs fixing.
3. **Run manually**: `uv run pre-commit run --all-files` to see all issues at once.

### Ruff Formatting Conflicts

If ruff makes changes you don't want:

1. Review the changes: `git diff`
2. Adjust the code to match ruff's expectations
3. Or configure ruff in `spiffworkflow-backend/pyproject.toml`

## Updating Hooks

To update pre-commit and its hooks:

```bash
# Update pre-commit itself
uv sync --upgrade-package pre-commit

# Update hook versions (if using remote hooks)
uv run pre-commit autoupdate
```

## Related Files

- `.pre-commit-config.yaml` - This configuration file
- `spiffworkflow-backend/pyproject.toml` - Ruff configuration (used by hooks)
- `bin/run_pre_commit_in_ci` - CI script for running hooks
- `bin/run_pyl` - Test script that includes pre-commit

## Additional Resources

- [Pre-commit Documentation](https://pre-commit.com/)
- [Ruff Documentation](https://docs.astral.sh/ruff/)
- [Pre-commit Hooks Repository](https://github.com/pre-commit/pre-commit-hooks)
