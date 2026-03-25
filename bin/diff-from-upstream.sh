#!/usr/bin/env bash
# diff-from-upstream.sh
# Fetches upstream and reports root-level files/folders that differ
# between the current branch and the upstream branch, including change type.
#
# Usage:
#   ./bin/diff-from-upstream.sh [remote-or-url] [upstream-branch]
#
# Defaults:
#   remote-or-url   = upstream
#   upstream-branch = main
#
# Examples:
#   ./bin/diff-from-upstream.sh
#   ./bin/diff-from-upstream.sh upstream main
#   ./bin/diff-from-upstream.sh https://github.com/sartography/spiff-arena main

set -euo pipefail

UPSTREAM_INPUT="${1:-upstream}"
UPSTREAM_BRANCH="${2:-main}"
DIFFLOG="difflog.txt"

# Detect whether the first arg is a URL or a named remote.
if [[ "${UPSTREAM_INPUT}" == http://* || "${UPSTREAM_INPUT}" == https://* || "${UPSTREAM_INPUT}" == git@* ]]; then
    IS_URL=true
else
    IS_URL=false
fi

echo "Fetching ${UPSTREAM_INPUT} (branch: ${UPSTREAM_BRANCH})..."

if [[ "${IS_URL}" == true ]]; then
    git fetch "${UPSTREAM_INPUT}" "${UPSTREAM_BRANCH}"
    UPSTREAM_REF="FETCH_HEAD"
    UPSTREAM_LABEL="${UPSTREAM_INPUT} @ ${UPSTREAM_BRANCH}"
else
    git fetch "${UPSTREAM_INPUT}"
    UPSTREAM_REF="${UPSTREAM_INPUT}/${UPSTREAM_BRANCH}"
    UPSTREAM_LABEL="${UPSTREAM_REF}"
fi

CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)

# Find the common ancestor so we compare only what diverged from upstream.
MERGE_BASE=$(git merge-base HEAD "${UPSTREAM_REF}")

# name-status gives lines like: "A\tpath", "M\tpath", "D\tpath", "R100\told\tnew"
# Local changes with status.
LOCAL_STATUS=$(git diff --name-status "${MERGE_BASE}" HEAD)

# Upstream changes (paths only — used to filter out overlapping roots).
UPSTREAM_CHANGED=$(git diff --name-only "${MERGE_BASE}" "${UPSTREAM_REF}")

# Map a git status letter to a human label.
status_label() {
    case "${1}" in
        A)  echo "ADDED"    ;;
        M)  echo "MODIFIED" ;;
        D)  echo "DELETED"  ;;
        R*) echo "RENAMED"  ;;
        C*) echo "COPIED"   ;;
        *)  echo "CHANGED"  ;;
    esac
}

# Extract the root-level component from a path.
root_of() { echo "${1%%/*}"; }

# Build a sorted unique list of root entries from upstream changed paths.
UPSTREAM_ROOTS=$(echo "${UPSTREAM_CHANGED}" | awk 'NF{print $1}' | awk -F/ '{print $1}' | sort -u)

# Collect unique local roots (to power the summary section).
LOCAL_ROOTS=$(echo "${LOCAL_STATUS}" | awk 'NF' | while IFS=$'\t' read -r status rest; do
    # For renames, the new path is the second tab field.
    path=$(echo "${rest}" | awk '{print $NF}')
    root_of "${path}"
done | sort -u)

# Roots that are local-only (not in upstream).
UNIQUE_LOCAL_ROOTS=$(comm -23 \
    <(echo "${LOCAL_ROOTS}" | sort) \
    <(echo "${UPSTREAM_ROOTS}" | sort))

{
    echo "Generated      : $(date)"
    echo "Current branch : ${CURRENT_BRANCH}"
    echo "Compared with  : ${UPSTREAM_LABEL}"
    echo "Merge base     : ${MERGE_BASE}"
    echo ""
    echo "============================================================"
    echo " Root-level entries changed locally but NOT in upstream"
    echo "============================================================"
    if [[ -z "${UNIQUE_LOCAL_ROOTS}" ]]; then
        echo "(none — all local changes overlap with upstream changes)"
    else
        while IFS= read -r entry; do
            [[ -z "${entry}" ]] && continue
            if [[ -d "${entry}" ]]; then
                kind="[dir] "
            elif [[ -f "${entry}" ]]; then
                kind="[file]"
            else
                kind="[gone]"
            fi
            echo "  ${kind}  ${entry}"
        done <<< "${UNIQUE_LOCAL_ROOTS}"
    fi

    echo ""
    echo "============================================================"
    echo " Detail: changed files unique to this branch (with change type)"
    echo "============================================================"
    if [[ -z "${LOCAL_STATUS}" ]]; then
        echo "(no local changes since diverging from upstream)"
    else
        echo "${LOCAL_STATUS}" | while IFS=$'\t' read -r status rest; do
            [[ -z "${status}" ]] && continue
            # For renames the path we care about is the destination (last field).
            path=$(echo "${rest}" | awk '{print $NF}')
            root=$(root_of "${path}")
            # Skip files whose root also appears in upstream changes.
            if echo "${UPSTREAM_ROOTS}" | grep -qx "${root}"; then
                continue
            fi
            label=$(status_label "${status}")
            printf "  %-10s %s\n" "[${label}]" "${path}"
        done
    fi
} | tee "${DIFFLOG}"

echo ""
echo "Output saved to: ${DIFFLOG}"
