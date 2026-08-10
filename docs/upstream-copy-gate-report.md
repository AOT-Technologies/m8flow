# Upstream-Copy CI Gate — Report

**Component:** `upstream-copy-check` job in `.github/workflows/ci.yml`
**Detector:** `bin/check-upstream-copying.py`
**Baseline:** `bin/upstream-copy-baseline.json`
**Tracking map:** `docs/upstream-license-compliance.md`
**Status:** active, enforced (blocking) on PRs to `main`

---

## 1. What it is

A CI gate that inspects the files a pull request changes and fails the build when
an Apache-2.0-licensed m8flow file is a copy of its gitignored, LGPL-2.1 upstream
(spiff-arena) counterpart. It is a **licensing-boundary guard**, not a general
code-quality or duplication linter.

It is deliberately zero-dependency (Python standard library only — `difflib`) and
runs against the real upstream source, which CI fetches at the pinned ref via
`bin/fetch-upstream.sh` before the check.

---

## 2. What issue it solves

The repository mixes two licenses across a patch/override architecture:

- **LGPL-2.1** — the imported upstream trees `spiffworkflow-backend/`,
  `spiffworkflow-frontend/`, `spiff-arena-common/`. These are gitignored and
  fetched on demand; they are not owned by this repo.
- **Apache-2.0** — the m8flow-owned trees `m8flow-backend/`, `m8flow-frontend/`,
  `extensions/`, and so on.

When upstream file bodies are pasted into the Apache-2.0 trees (rather than
overridden thinly or re-expressed independently), LGPL-licensed expression ends up
inside the Apache-2.0 boundary. A prior audit found **65 files** substantially
line-identical to upstream, and one carrying a verbatim upstream attribution
comment (`jasquat/burnettk - 2022-12-28`).

The gate stops the problem from growing: it **blocks new copying and regressions**
while a separate, tracked effort pays down the existing copies. It does not force
an immediate mass rewrite.

---

## 3. How it works

The detector resolves each changed Apache file to its upstream counterpart in
three steps: (1) **path convention** — `m8flow-backend/src/m8flow_backend/X` ↔
`spiffworkflow-backend/src/spiffworkflow_backend/X`, `m8flow-frontend/src/X` ↔
`spiffworkflow-frontend/src/X`; (2) a **basename search** for renamed files;
(3) a **content-addressed search** across the whole upstream tree (an inverted
line-hash index, confirmed with precise ratio/block metrics) for copies pasted
into differently-named files. It then applies four independent layers; **any**
layer can fail a PR:

| Layer | Signal | Grandfathered by baseline? |
|---|---|---|
| A | Whole-file line similarity ≥ **0.50** vs the counterpart | Yes |
| B | Longest run of ≥ **40** contiguous identical lines | Yes |
| C1 | LGPL/GPL header text, or upstream attribution (author handles, `sartography/` URLs) | **No — always fails** |
| C2 | Verbatim distinctive comment (≥ 40 chars) also present in the counterpart | Yes |

Layers B and C exist because a percentage alone is not enough: a mostly-original
file can still paste in a give-away comment (C2/C1), and a partial copy can dilute
its whole-file ratio below the threshold while still lifting a large block (B).

**Baseline behavior.** `bin/upstream-copy-baseline.json` records today's copy
signals for the 65 known files. The gate fails only when a file exceeds the
threshold **and** moves beyond its baseline (small drift allowed: ±0.02 ratio,
±5 lines) — i.e. *new* copying or a *regression*. Remediated files naturally drop
out of the baseline. **C1 markers are never grandfathered** — a license header or
attribution comment fails even if the file is in the baseline.

**Where it runs.** Only on `pull_request` events targeting `main` that change
`m8flow-backend/**` or `m8flow-frontend/**`, and it is wired into the `required-ci`
merge gate. It is skipped on plain pushes, `workflow_dispatch`, and PRs that do
not touch backend/frontend code.

---

## 4. What it can currently do

- Detect near-verbatim and partial copies of upstream files placed at the
  conventional override path (the common case for this repo's architecture).
- Catch a copy pasted into a **brand-new, differently-named file** with no
  matching upstream path or basename, via a content-addressed search across the
  upstream tree (attributed to the real source file). Conservative by design: it
  only flags a file that clears the ratio or contiguous-block bar, so genuinely
  original files are not falsely attributed.
- Catch partial lifts that stay under 50% overall, via the contiguous-block layer.
- Hard-fail on LGPL/GPL license header text regardless of similarity score.
- Hard-fail on upstream attribution left in comments (author handles,
  `sartography/` repo URLs) regardless of similarity score.
- Flag verbatim copied comments even in otherwise-original files.
- Distinguish **new copying / regressions** from **pre-existing** copies via the
  checked-in baseline, so it does not block unrelated work on already-flagged files.
- Run with zero new dependencies, against the exact pinned upstream version.
- Support local use and re-baselining: `--all` (full-tree report),
  `--diff <ref>` (PR mode), `--write-baseline`, `--report-only`, `--json`.

---

## 5. What it cannot currently do

- **Resist deliberate evasion by heavy reformatting + identifier renaming.**
  All layers (and the content-addressed search) compare raw/whitespace-stripped
  lines, so reflowing *and* renaming identifiers together can lower the scores
  below the thresholds. Renaming the *file* alone no longer evades (the content
  search handles that), and reindentation alone is largely tolerated, but a
  determined line-level rewrite can still slip under. A token/AST-based tool
  (e.g. jscpd) would resist this; it was evaluated and intentionally left out
  because it does not fit the 1-to-1 external comparison, cannot see attribution
  comments, and would require rebuilding the baseline. It remains a possible
  future *code-health* add-on, not part of this gate.
- **Catch a copy diluted below the thresholds.** The content search only attaches
  a counterpart that already clears the ratio or contiguous-block bar. A small
  snippet lifted into a large, otherwise-original, differently-named file can stay
  under both bars and go unflagged (unless it carries a C1 marker).
- **Detect internal (m8flow-to-m8flow) duplication.** The gate only compares
  against upstream; it is not a general copy-paste detector.
- **Make a legal determination.** It is a static heuristic that flags likely
  license-boundary violations for human review; it does not assert infringement.
- **Run outside a pull request.** It needs the PR base ref for the diff, so it does
  not run on pushes or manual dispatch.
- **Remediate anything.** It only detects. Rewriting flagged files (preserving the
  functional contract — column names/types, exported API — while re-expressing
  boilerplate independently) is a separate effort tracked in
  `docs/upstream-license-compliance.md`.
- **Judge whether copying is legally permissible.** It treats functional contracts
  (schema column names/types) the same as expressive code for scoring; humans must
  decide what is acceptable to keep.

---

## 6. Operating it

```bash
# Prerequisite: fetch the gitignored upstream trees at the pinned ref
./bin/fetch-upstream.sh

# What a PR sees (changed files vs base):
bin/check-upstream-copying.py --diff origin/main

# Full-tree audit (report only, no fail semantics beyond markers):
bin/check-upstream-copying.py --all

# Regenerate the baseline after an intentional, reviewed change to a flagged file:
bin/check-upstream-copying.py --all --write-baseline bin/upstream-copy-baseline.json
```

**Tuning knobs:** `--threshold` (default 0.50), `--block-lines` (default 40),
`--report-only` (print but never fail — the rollout/rollback lever). Marker
patterns for C1 live in `MARKER_PATTERNS` in the script and are meant to be
extended conservatively (a marker must be something that should never legitimately
appear in m8flow-owned code).
