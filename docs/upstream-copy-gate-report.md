# Upstream-Copy CI Gate — Report

**Components:** `upstream-copy-check` and `upstream-cpd-check` jobs in `.github/workflows/ci.yml`
**Detectors:** `bin/check-upstream-copying.py` (raw-line) + `bin/check-upstream-cpd.py` (PMD CPD, token-level)
**Baselines (source of truth for currently-flagged files):** `bin/upstream-copy-baseline.json`, `bin/upstream-cpd-baseline.json`
**Status:** active, enforced (blocking) on PRs to `main`

---

## 1. What it is

Two complementary CI gates that fail the build when an Apache-2.0-licensed m8flow
file is a copy of its gitignored, LGPL-2.1 upstream (spiff-arena) counterpart. They
are **licensing-boundary guards**, not general code-quality or duplication linters.

- **`upstream-copy-check`** — a zero-dependency raw-line detector (Python stdlib
  `difflib`). Cross-language, comment-aware, fast; runs over the files a PR changes.
- **`upstream-cpd-check`** — a token-level detector using **PMD CPD**. Because it
  tokenizes source, it catches copies that were reformatted, reindented, or had
  identifiers renamed to dodge the raw-line gate. Runs a whole-tree cross-tree
  clone scan. Requires Java + PMD (installed in CI).

Both run against the real upstream source, which CI fetches at the pinned ref via
`bin/fetch-upstream.sh` before the checks.

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

**Token-level gate (`upstream-cpd-check`).** In parallel, PMD CPD scans both trees
and reports **cross-tree token clones** — a duplicated token block present in both
an owned m8flow tree and an upstream tree. It runs with `--ignore-identifiers
--ignore-literals` (minimum 75 tokens), so a copy that was reformatted, reindented,
or had identifiers/literals renamed is still matched. Python is scanned directly;
frontend `.tsx`/`.jsx` are staged into a `.ts`-named temp tree first, because CPD's
`typescript` language only reads `.ts` (its lexer tokenizes JSX fine once the
extension is `.ts`). It has its own baseline, `bin/upstream-cpd-baseline.json`, and
fails on new cross-tree clones or regressions (a larger duplicated block). It is
**fail-closed**: missing upstream trees, CPD parse/launch errors, or recovering
fewer than half of on-disk baseline pairs all fail the job instead of reporting
a clean PASS.

**Where they run.** Only on `pull_request` events targeting `main` that change
`m8flow-backend/**` or `m8flow-frontend/**`, and both are wired into the
`required-ci` merge gate. They are skipped on plain pushes, `workflow_dispatch`,
and PRs that do not touch backend/frontend code.

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
- **Catch a copy that was reformatted, reindented, or had identifiers/literals
  renamed** to dodge the raw-line gate — via the token-level CPD gate. Verified: a
  copy of an upstream model with `Group`→`Squad` renaming, blank lines removed, and
  4→2-space reindentation drops to 0.24 raw-line similarity (missed by the line
  gate) but is still caught by CPD.
- Cover frontend `.tsx`/`.jsx` at the token level (via `.ts` staging), not just
  Python.
- Distinguish **new copying / regressions** from **pre-existing** copies via the
  checked-in baselines, so it does not block unrelated work on already-flagged files.
- Run the raw-line gate with zero dependencies; the CPD gate adds only Java + PMD
  in CI. Both run against the exact pinned upstream version.
- Support local use and re-baselining: raw-line gate `--all` / `--diff <ref>` /
  `--write-baseline` / `--report-only` / `--json`; CPD gate `--write-baseline` /
  `--report-only` / `--min-tokens`.

---

## 5. What it cannot currently do

- **Catch a small, heavily-obfuscated snippet below the token/line floors.** The
  CPD gate needs ≥ 75 duplicated tokens (~12–18 lines); the raw-line gate needs
  ≥ 50% similarity or a ≥ 40-line block. A short fragment that is both reworded and
  reindented can fall under both floors. Lowering the floors trades this for more
  false positives on structurally-similar boilerplate.
- **Resist a full structural rewrite.** Token-level detection survives reformatting
  and renaming, but rewriting the control flow / statement structure (not just
  names and whitespace) defeats it. Only semantic/AST-equivalence analysis would
  catch that, and it is out of scope.
- **Detect internal (m8flow-to-m8flow) duplication.** Both gates only compare
  against upstream; they are not general copy-paste detectors.
- **Make a legal determination.** They are static heuristics that flag likely
  license-boundary violations for human review; they do not assert infringement.
- **Run outside a pull request.** They run only on PRs touching backend/frontend
  (the raw-line gate additionally needs the PR base ref for its diff).
- **Remediate anything.** It only detects. Rewriting flagged files is a separate
  effort — see §7.
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

# Regenerate the raw-line baseline after an intentional, reviewed change:
bin/check-upstream-copying.py --all --write-baseline bin/upstream-copy-baseline.json

# Token-level gate (needs PMD 7: set $PMD_BIN or put `pmd` on PATH):
bin/check-upstream-cpd.py                                             # gate
bin/check-upstream-cpd.py --report-only                              # see everything
bin/check-upstream-cpd.py --write-baseline bin/upstream-cpd-baseline.json  # re-baseline
```

**Tuning knobs (raw-line):** `--threshold` (default 0.50), `--block-lines`
(default 40), `--report-only`. Marker patterns for C1 live in `MARKER_PATTERNS`
and should be extended conservatively (a marker must be something that should never
legitimately appear in m8flow-owned code).

**Tuning knobs (CPD):** `--min-tokens` (default 75), `--no-ignore-identifiers` /
`--no-ignore-literals` (less rename-resistant, fewer false positives),
`--report-only`. PMD version is pinned in `.github/workflows/ci.yml`.

---

## 7. Remediation & tracking

The gates block *new* copying and *regressions*; the copies that already exist are
grandfathered so no immediate mass rewrite is forced. Paying that debt down is a
separate, ongoing effort.

**Where the flagged files live.** The two baseline JSONs are the source of truth
for what is currently flagged — `bin/upstream-copy-baseline.json` (raw-line: per
file, ratio / longest block / comment matches) and `bin/upstream-cpd-baseline.json`
(token-level: owned ↔ upstream clone pairs and token counts). A file drops out of a
baseline automatically once it no longer trips that gate, so the baselines shrink as
remediation lands. Track the work itself through issues/PRs rather than a separate
checklist.

**How to remediate.**
- **Backend models** cannot be deleted (no fallback). Preserve the *functional
  contract* — column names/types, table names, exported API (these are not
  copyrightable expression) — but re-express the surrounding boilerplate
  independently (own structure and comments). Route changes through the non-admin
  regression check in `AGENTS.md` (`editor`/`reviewer` → `GET /v1.0/onboarding`,
  `GET /v1.0/tasks`).
- **Frontend files** should shrink to only the tenant/RBAC delta and wrap the
  upstream component through the override resolver, instead of forking its full body.
- **Attribution/markers first.** The `jasquat/burnettk` comment in
  `ProcessInstanceListTableWithFilters.tsx` is a C1 marker: it hard-fails any PR
  that touches the file until removed, and is never grandfathered.

**Intentional, reviewed changes to a flagged file.** If a change legitimately alters
an already-flagged file, regenerate the relevant baseline (`--write-baseline`) and
get that diff reviewed alongside the code change, so the grandfathered numbers move
deliberately, not silently.
