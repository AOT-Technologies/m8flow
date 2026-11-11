"""Behaviour tests for the release workflows' own shell logic.

These run the real `run:` blocks out of the workflow files, so the gating a
release depends on is exercised rather than described. Releases are build
once: a merge to main publishes sha-<commit>, an rc retags it, and a GA retags
the rc. The tests cover the parts that are easy to get wrong and expensive to
find out about at release time:

* the inputs accept exactly one shape per channel, and a GA names its
  candidate explicitly (2.0.0 promotes 2.0.8-rc, never a derived 2.0.0-rc);
* the released commit: a GA is its candidate's own commit, an rc is on main,
  and an existing release tag is never moved;
* which build each component ships: the last first-parent commit that changed
  its files, so a merge commit's image is found and a later unrelated merge
  does not hide it;
* a missing image stops the release, except an rc at the tip of main, which
  builds it once;
* the summary fails any release that did not tag every image (and, for a GA,
  the git tag and the GitHub Release).

The blocks are extracted textually rather than with a YAML parser, because the
runner that executes these tests (check-migrations.yml) installs no packages.
Extraction is scoped to one job and refuses an ambiguous or missing step, so a
renamed or duplicated step fails the suite instead of silently testing the
wrong script.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
BASH = shutil.which("bash")
GIT = shutil.which("git")


class WorkflowExtractionError(AssertionError):
    """Raised with enough context to fix a workflow edit that broke a test."""


def _job_block(source: str, job: str, where: str) -> str:
    """Return the text of one job, so a step name only has to be unique in it."""
    start = re.search(rf"(?m)^  {re.escape(job)}:$", source)
    if start is None:
        jobs = re.findall(r"(?m)^  ([a-z0-9][\w-]*):$", source)
        raise WorkflowExtractionError(
            f"{where}: no job named {job!r}. Jobs present: {', '.join(jobs) or 'none'}."
        )
    rest = source[start.end():]
    end = re.search(r"(?m)^  \S", rest)
    return rest[: end.start()] if end else rest


def extract_run_block(workflow: str, job: str, step_name: str) -> str:
    """Return the `run:` script of one step of one job, dedented.

    Scoped to `job` and required to match exactly once inside it: a duplicated
    or renamed step raises instead of quietly returning the wrong script.
    """
    source = (WORKFLOWS / workflow).read_text(encoding="utf-8")
    return _extract(source, job, step_name, f"{workflow} job {job!r} step {step_name!r}")


def _extract(source: str, job: str, step_name: str, where: str) -> str:
    block = _job_block(source, job, where)

    marker = f"- name: {step_name}\n"
    hits = [m.start() for m in re.finditer(re.escape(marker), block)]
    if len(hits) != 1:
        names = re.findall(r"(?m)^\s*- name: (.+)$", block)
        raise WorkflowExtractionError(
            f"{where}: expected exactly one such step, found {len(hits)}. "
            f"Steps in this job: {names}. "
            "Rename the step or scope this test to the right job."
        )

    body = block[hits[0]:]
    run = re.search(r"(?m)^(\s*)run: \|-?\n", body)
    if run is None:
        head = "\n".join(body.split("\n")[:8])
        raise WorkflowExtractionError(
            f"{where}: no literal 'run: |' block. A folded scalar or a `run:` on "
            f"one line cannot be extracted. Step begins:\n{head}"
        )
    indent = len(run.group(1))

    lines: list[str] = []
    for line in body[run.end():].split("\n"):
        if line.strip() and len(line) - len(line.lstrip()) <= indent:
            break
        lines.append(line)
    script = textwrap.dedent("\n".join(lines))

    # A GitHub expression is interpolated before the runner sees the script, so
    # a block containing one cannot be executed as written; it belongs in env.
    if "${{" in script:
        raise WorkflowExtractionError(
            f"{where}: the script interpolates a ${{{{ }}}} expression, so it "
            "cannot run outside Actions. Move the value into the step's env."
        )
    return script


def parse_github_file(text: str) -> dict[str, str]:
    """Read a $GITHUB_ENV / $GITHUB_OUTPUT file the way the runner does.

    Both forms, because a step is free to switch between them: `key=value`,
    and the heredoc `key<<DELIM` ... `DELIM` that any value containing a
    newline has to use. Parsing only the first would quietly return nothing
    for a multi-line value and turn a real assertion into a passing test.
    """
    written: dict[str, str] = {}
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        index += 1
        heredoc = re.fullmatch(r"([^=<]+)<<([A-Za-z_][\w]*)", line)
        if heredoc:
            key, delimiter = heredoc.group(1), heredoc.group(2)
            body: list[str] = []
            while index < len(lines) and lines[index] != delimiter:
                body.append(lines[index])
                index += 1
            if index >= len(lines):
                raise AssertionError(f"{key}<<{delimiter} is never closed")
            index += 1  # the delimiter itself
            written[key] = "\n".join(body)
        elif "=" in line:
            key, _, value = line.partition("=")
            written[key] = value
    return written


class GitHubFileParsing(unittest.TestCase):
    """The helper that reads back what a step wrote."""

    def test_plain_assignments(self):
        self.assertEqual(
            parse_github_file("tag=2.0.0\nrc_tag=2.0.8-rc\n"),
            {"tag": "2.0.0", "rc_tag": "2.0.8-rc"},
        )

    def test_a_heredoc_value_keeps_its_newlines(self):
        written = parse_github_file(
            "images<<IMAGES_EOF\nm8flow/m8flow-backend\nm8flow/m8flow-mcp\nIMAGES_EOF\ntag=2.0.0\n"
        )
        self.assertEqual(written["images"], "m8flow/m8flow-backend\nm8flow/m8flow-mcp")
        self.assertEqual(written["tag"], "2.0.0")

    def test_a_value_containing_an_equals_sign_is_kept_whole(self):
        self.assertEqual(parse_github_file("url=a=b\n"), {"url": "a=b"})

    def test_an_unterminated_heredoc_is_an_error(self):
        with self.assertRaises(AssertionError):
            parse_github_file("images<<EOF\nm8flow/m8flow-backend\n")


class Extractor(unittest.TestCase):
    """The extractor itself: it must fail loudly rather than guess."""

    SYNTHETIC = textwrap.dedent(
        """\
        jobs:
          first:
            steps:
              - name: Report
                run: |
                  echo "first job"
          second:
            steps:
              - name: Report
                run: |
                  echo "second job"
              - name: Report
                run: |
                  echo "duplicate in the same job"
        """
    )

    def test_a_step_name_is_scoped_to_its_job(self):
        """The same step name in an earlier job must not be picked up."""
        script = _extract(self.SYNTHETIC, "first", "Report", "synthetic")
        self.assertIn("first job", script)
        self.assertNotIn("second job", script)

    def test_a_duplicated_step_name_is_refused(self):
        with self.assertRaises(WorkflowExtractionError) as caught:
            _extract(self.SYNTHETIC, "second", "Report", "synthetic")
        message = str(caught.exception)
        self.assertIn("found 2", message)
        self.assertIn("Report", message)

    def test_a_renamed_step_is_refused_and_lists_the_real_names(self):
        with self.assertRaises(WorkflowExtractionError) as caught:
            _extract(self.SYNTHETIC, "first", "Summary", "synthetic")
        message = str(caught.exception)
        self.assertIn("found 0", message)
        self.assertIn("Report", message)

    def test_a_step_without_a_literal_run_block_is_refused(self):
        source = textwrap.dedent(
            """\
            jobs:
              only:
                steps:
                  - name: Report
                    run: echo "one line"
            """
        )
        with self.assertRaises(WorkflowExtractionError) as caught:
            _extract(source, "only", "Report", "synthetic")
        self.assertIn("no literal 'run: |' block", str(caught.exception))

    def test_a_step_that_interpolates_an_expression_is_refused(self):
        source = textwrap.dedent(
            """\
            jobs:
              only:
                steps:
                  - name: Report
                    run: |
                      echo "${{ needs.tag.result }}"
            """
        )
        with self.assertRaises(WorkflowExtractionError) as caught:
            _extract(source, "only", "Report", "synthetic")
        self.assertIn("env", str(caught.exception))

    def test_an_unknown_job_names_the_jobs_that_exist(self):
        with self.assertRaises(WorkflowExtractionError) as caught:
            _job_block(self.SYNTHETIC, "third", "synthetic")
        self.assertIn("first", str(caught.exception))
        self.assertIn("second", str(caught.exception))

    def test_every_step_this_suite_extracts_still_resolves(self):
        for workflow, job, step in (
            ("release.yaml", "summary", "Report"),
            ("release.yaml", "branch", "Release channel"),
            ("release.yaml", "plan", "Resolve commit"),
            ("release.yaml", "plan", "Resolve sources"),
            ("release.yaml", "plan", "Check the registry"),
            ("release.yaml", "version", "Check the tag"),
            ("release.yaml", "git-tag", "Create the release tag"),
            ("github-release.yml", "build", "Validate version"),
            ("github-release.yml", "build", "Verify the tag marks a candidate"),
        ):
            with self.subTest(workflow=workflow, job=job, step=step):
                self.assertTrue(extract_run_block(workflow, job, step).strip())


@unittest.skipIf(BASH is None, "bash is unavailable")
class ShellStep(unittest.TestCase):
    def run_step(self, script: str, env: dict[str, str], path_prefix: str | None = None):
        """Run a step's script with GitHub's files wired up. Returns (rc, output, written)."""
        with tempfile.TemporaryDirectory() as tmp:
            paths = {name: os.path.join(tmp, name) for name in ("summary", "env", "output")}
            for path in paths.values():
                open(path, "w").close()
            script_path = os.path.join(tmp, "step.sh")
            with open(script_path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(script)

            child = {
                **os.environ,
                "GITHUB_STEP_SUMMARY": paths["summary"],
                "GITHUB_ENV": paths["env"],
                "GITHUB_OUTPUT": paths["output"],
                **env,
            }
            if path_prefix:
                child["PATH"] = path_prefix + os.pathsep + child["PATH"]

            proc = subprocess.run(
                [BASH, script_path], capture_output=True, text=True, env=child
            )
            written = {}
            for name in ("env", "output"):
                written.update(parse_github_file(Path(paths[name]).read_text(encoding="utf-8")))
            output = proc.stdout + proc.stderr + Path(paths["summary"]).read_text(encoding="utf-8")
            return proc.returncode, output, written


def install_shim(directory: str, name: str, body: str) -> None:
    """Write an executable Python shim called `name` that bash finds on PATH."""
    py = os.path.join(directory, f"{name}_impl.py")
    with open(py, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(body)
    launcher = os.path.join(directory, name)
    with open(launcher, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(f'#!/bin/sh\nexec "{sys.executable}" "{py}" "$@"\n')
    # Owner-only: nothing else on the machine has any business executing it.
    os.chmod(launcher, 0o700)


class ReleaseChannelInput(ShellStep):
    """release.yaml, branch/Release channel: which inputs each channel takes."""

    def setUp(self) -> None:
        self.script = extract_run_block("release.yaml", "branch", "Release channel")

    def check(self, channel: str, tag_name: str = "", rc_tag: str = "", commit_sha: str = "") -> int:
        rc, _, _ = self.run_step(self.script, {
            "CHANNEL": channel, "TAG_NAME": tag_name, "RC_TAG": rc_tag, "COMMIT_SHA": commit_sha,
        })
        return rc

    def test_ga_takes_a_plain_version_and_a_named_candidate(self):
        self.assertEqual(self.check("ga", "2.0.0", "2.0.8-rc"), 0)
        self.assertEqual(self.check("ga", "2.0.0", "2.0.0-rc"), 0)

    def test_ga_refuses_any_other_release_tag(self):
        for rejected in ("2.0.0-ga", "2.0.0-rc", "v2.0.0", "2.0", "2.0.0.1", ""):
            with self.subTest(tag_name=rejected):
                self.assertEqual(self.check("ga", rejected, "2.0.8-rc"), 1)

    def test_ga_requires_the_candidate_to_be_named(self):
        """Never derived: 2.0.0-rc also exists and is not what was tested."""
        for rejected in ("", "2.0.8", "2.0.8-ga", "v2.0.8-rc", "2.0.8-rc1"):
            with self.subTest(rc_tag=rejected):
                self.assertEqual(self.check("ga", "2.0.0", rejected), 1)

    def test_ga_refuses_a_commit(self):
        """A GA release is the candidate's commit; there is nothing to choose."""
        self.assertEqual(self.check("ga", "2.0.0", "2.0.8-rc", "abc1234"), 1)

    def test_rc_takes_an_rc_tag_or_nothing(self):
        self.assertEqual(self.check("rc", "2.1.0-rc"), 0)
        self.assertEqual(self.check("rc", ""), 0, "empty means auto-increment")
        self.assertEqual(self.check("rc", "", commit_sha="abc1234"), 0)
        for rejected in ("2.0.7", "2.0.7-ga", "v2.0.7-rc", "2.0.7-rc1"):
            with self.subTest(tag_name=rejected):
                self.assertEqual(self.check("rc", rejected), 1)

    def test_rc_refuses_a_candidate_input(self):
        self.assertEqual(self.check("rc", "", "2.0.8-rc"), 1)


@unittest.skipIf(BASH is None or GIT is None, "bash or git is unavailable")
class GitRepoStep(ShellStep):
    """A throwaway repository shaped like main: merge commits on first parent.

        root ── m1 (merge: backend) ── m2 (merge: designer) ── m3 (merge: docs)
                 └ b1 (backend)          └ d1 (designer)        └ x1 (docs)

    Tags: m1 is 2.0.0-rc, m2 is 2.0.8-rc. A side branch `other` holds a commit
    that is not on main.
    """

    def git(self, *args: str) -> str:
        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid",
            "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
        }
        return subprocess.run(
            [GIT, *args], cwd=self.repo, env=env, check=True, capture_output=True, text=True
        ).stdout.strip()

    def commit_file(self, path: str, message: str) -> str:
        full = Path(self.repo, path)
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(message + "\n", encoding="utf-8")
        self.git("add", path)
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD")

    def merge(self, branch: str, path: str, message: str) -> str:
        self.git("checkout", "-q", "-b", branch)
        self.commit_file(path, f"{branch} change")
        self.git("checkout", "-q", "main")
        self.git("merge", "-q", "--no-ff", branch, "-m", message)
        return self.git("rev-parse", "HEAD")

    def setUp(self) -> None:
        self.repo = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.repo, True)
        self.git("init", "-q", "-b", "main")
        self.root = self.commit_file("README.md", "root")
        self.m1 = self.merge("b1", "m8flow-backend/app.py", "merge backend")
        self.git("tag", "-a", "2.0.0-rc", "-m", "rc", self.m1)
        self.m2 = self.merge("d1", "m8flow-designer/src/app.tsx", "merge designer")
        self.git("tag", "-a", "2.0.8-rc", "-m", "rc", self.m2)
        self.m3 = self.merge("x1", "docs/readme.md", "merge docs")
        self.git("checkout", "-q", "-b", "other", self.root)
        self.off_main = self.commit_file("m8flow-backend/stray.py", "not on main")
        self.git("checkout", "-q", "main")

    def run_in_repo(self, script: str, env: dict[str, str], path_prefix: str | None = None):
        return self.run_step(f'cd "{self.repo}"\n' + script, env, path_prefix)


class ResolveCommit(GitRepoStep):
    """release.yaml, plan/Resolve commit: which commit a release marks."""

    def setUp(self) -> None:
        super().setUp()
        self.script = extract_run_block("release.yaml", "plan", "Resolve commit")

    def resolve(self, **env: str):
        base = {"CHANNEL": "rc", "TAG_NAME": "", "RC_TAG": "", "COMMIT_SHA": "", "RUN_SHA": self.m3}
        return self.run_in_repo(self.script, {**base, **env})

    def test_rc_defaults_to_the_tip_of_main(self):
        rc, output, written = self.resolve()
        self.assertEqual(rc, 0, output)
        self.assertEqual(written["commit"], self.m3)
        self.assertEqual(written["tag_exists"], "false")

    def test_rc_takes_an_earlier_main_commit(self):
        rc, output, written = self.resolve(COMMIT_SHA=self.m1[:10])
        self.assertEqual(rc, 0, output)
        self.assertEqual(written["commit"], self.m1, "abbreviations resolve to the full SHA")

    def test_rc_refuses_a_commit_that_is_not_on_main(self):
        rc, output, _ = self.resolve(COMMIT_SHA=self.off_main)
        self.assertEqual(rc, 1, output)
        self.assertIn("not on main", output)

    def test_rc_refuses_an_unknown_commit(self):
        rc, output, _ = self.resolve(COMMIT_SHA="0" * 40)
        self.assertEqual(rc, 1, output)

    def test_ga_is_the_named_candidates_commit(self):
        """2.0.0 from 2.0.8-rc: the commit is m2, not 2.0.0-rc's m1."""
        rc, output, written = self.resolve(CHANNEL="ga", TAG_NAME="2.0.0", RC_TAG="2.0.8-rc")
        self.assertEqual(rc, 0, output)
        self.assertEqual(written["commit"], self.m2)
        self.assertEqual(written["tag_exists"], "false")

    def test_ga_refuses_a_missing_candidate(self):
        rc, output, _ = self.resolve(CHANNEL="ga", TAG_NAME="2.0.0", RC_TAG="2.0.9-rc")
        self.assertEqual(rc, 1, output)
        self.assertIn("2.0.9-rc", output)

    def test_ga_rerun_keeps_a_release_tag_already_on_the_candidate(self):
        self.git("tag", "-a", "2.0.0", "-m", "release", self.m2)
        rc, output, written = self.resolve(CHANNEL="ga", TAG_NAME="2.0.0", RC_TAG="2.0.8-rc")
        self.assertEqual(rc, 0, output)
        self.assertEqual(written["tag_exists"], "true")

    def test_ga_never_moves_a_release_tag_on_another_commit(self):
        self.git("tag", "2.0.0", self.m3)
        rc, output, _ = self.resolve(CHANNEL="ga", TAG_NAME="2.0.0", RC_TAG="2.0.8-rc")
        self.assertEqual(rc, 1, output)
        self.assertIn("never moved", output)


class ResolveSources(GitRepoStep):
    """release.yaml, plan/Resolve sources: which build each component ships."""

    COMPONENTS = (
        "backend\tm8flow/m8flow-backend\tm8flow-backend/** docker/m8flow.backend.Dockerfile \tbackend-cicd.yaml\n"
        "designer\tm8flow/m8flow-designer\tm8flow-designer/** m8flow-bpmn/** \tdesigner-cicd.yaml\n"
    )

    def setUp(self) -> None:
        super().setUp()
        self.script = extract_run_block("release.yaml", "plan", "Resolve sources")
        self.components = os.path.join(self.repo, ".components.tsv")
        self.sources = os.path.join(self.repo, ".sources.tsv")
        Path(self.components).write_text(self.COMPONENTS, encoding="utf-8")

    def resolve(self, **env: str):
        base = {
            "CHANNEL": "rc", "COMMIT": self.m3, "RC_TAG": "",
            "COMPONENTS_FILE": self.components, "SOURCES_FILE": self.sources,
        }
        rc, output, _ = self.run_in_repo(self.script, {**base, **env})
        lines = Path(self.sources).read_text(encoding="utf-8").splitlines() if os.path.exists(self.sources) else []
        return rc, output, {line.split("\t")[0]: line.split("\t")[2] for line in lines}

    def test_each_component_ships_its_last_merge_that_changed_it(self):
        """m3 changed only docs: backend is m1's build, designer m2's."""
        rc, output, sources = self.resolve()
        self.assertEqual(rc, 0, output)
        self.assertEqual(sources, {"backend": f"sha-{self.m1}", "designer": f"sha-{self.m2}"})

    def test_the_merge_commit_is_found_not_the_branch_commit(self):
        """The push to main built the merge commit; b1 never had an image."""
        rc, output, sources = self.resolve()
        self.assertEqual(rc, 0, output)
        b1 = self.git("rev-parse", "b1")
        self.assertNotEqual(sources["backend"], f"sha-{b1}")

    def test_an_earlier_candidate_ignores_later_merges(self):
        """At m1 the designer has never changed, so it has no build to ship."""
        rc, output, _ = self.resolve(COMMIT=self.m1)
        self.assertEqual(rc, 1, output)
        self.assertIn("designer", output)

    def test_ga_ships_the_candidates_own_images(self):
        rc, output, sources = self.resolve(CHANNEL="ga", COMMIT=self.m2, RC_TAG="2.0.8-rc")
        self.assertEqual(rc, 0, output)
        self.assertEqual(sources, {"backend": "2.0.8-rc", "designer": "2.0.8-rc"})

    def test_each_source_names_the_workflow_that_builds_it(self):
        """The registry check asks GitHub about that workflow's runs."""
        rc, output, _ = self.resolve()
        self.assertEqual(rc, 0, output)
        rows = [line.split("\t") for line in Path(self.sources).read_text(encoding="utf-8").splitlines()]
        self.assertEqual({row[0]: row[3] for row in rows},
                         {"backend": "backend-cicd.yaml", "designer": "designer-cicd.yaml"})


# A stand-in for `docker buildx imagetools inspect --raw <ref>`: succeeds for
# the refs listed in FAKE_EXISTING (space-separated), fails for any other.
FAKE_DOCKER = """\
import os, sys
ref = sys.argv[-1]
existing = os.environ.get("FAKE_EXISTING", "").split()
if sys.argv[1:4] != ["buildx", "imagetools", "inspect"]:
    sys.exit(f"fake docker: unexpected call {sys.argv[1:]}")
if ref in existing:
    print('{"schemaVersion": 2}')
    sys.exit(0)
sys.exit(1)
"""

# A stand-in for `gh`: logs its arguments to FAKE_GH_LOG, fails when
# FAKE_GH_FAILS=1, and otherwise prints FAKE_GH_OUTPUT. A test reads the log
# to check what the step asked GitHub.
FAKE_GH_LOGGING = """\
import json, os, sys
with open(os.environ["FAKE_GH_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps(sys.argv[1:]) + "\\n")
if os.environ.get("FAKE_GH_FAILS") == "1":
    sys.exit(1)
print(os.environ.get("FAKE_GH_OUTPUT", ""))
"""


def gh_calls(log: str) -> list[list[str]]:
    if not os.path.exists(log):
        return []
    return [json.loads(line) for line in Path(log).read_text(encoding="utf-8").splitlines()]


@unittest.skipIf(BASH is None, "bash is unavailable")
class CheckTheRegistry(ShellStep):
    """release.yaml, plan/Check the registry: reuse, build once, or stop."""

    TIP = "c" * 40
    OLD = "a" * 40

    def setUp(self) -> None:
        self.script = extract_run_block("release.yaml", "plan", "Check the registry")
        self.bin = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.bin, True)
        install_shim(self.bin, "docker", FAKE_DOCKER)
        install_shim(self.bin, "gh", FAKE_GH_LOGGING)
        self.gh_log = os.path.join(self.bin, "gh.log")
        self.sources = os.path.join(self.bin, "sources.tsv")
        Path(self.sources).write_text(
            f"backend\tm8flow/m8flow-backend\tsha-{self.OLD}\tbackend-cicd.yaml\n"
            f"node-wire-proxy\tm8flow/m8flow-node-wire-proxy\tsha-{self.OLD}\tnode-wire-proxy-cicd.yaml\n",
            encoding="utf-8",
        )

    def check(self, existing: list[str], **env: str):
        base = {
            "GH_TOKEN": "x", "REPO": "AOT-Technologies/m8flow",
            "CHANNEL": "rc", "COMMIT": self.TIP, "RUN_SHA": self.TIP,
            "SOURCES_FILE": self.sources, "FAKE_EXISTING": " ".join(existing),
            "FAKE_GH_LOG": self.gh_log, "FAKE_GH_OUTPUT": "0",
        }
        return self.run_step(self.script, {**base, **env}, path_prefix=self.bin)

    BOTH = [
        f"docker.io/m8flow/m8flow-backend:sha-{'a' * 40}",
        f"docker.io/m8flow/m8flow-node-wire-proxy:sha-{'a' * 40}",
    ]

    def test_existing_images_are_reused_and_nothing_is_built(self):
        rc, output, written = self.check(self.BOTH)
        self.assertEqual(rc, 0, output)
        self.assertEqual(written["build_backend"], "false")
        self.assertEqual(written["build_node_wire_proxy"], "false")
        self.assertEqual(written["sources"].splitlines(), [
            f"m8flow/m8flow-backend sha-{self.OLD}",
            f"m8flow/m8flow-node-wire-proxy sha-{self.OLD}",
        ])

    def test_a_missing_image_at_the_tip_is_built_once_from_the_tip(self):
        rc, output, written = self.check(self.BOTH[:1])
        self.assertEqual(rc, 0, output)
        self.assertEqual(written["build_backend"], "false")
        self.assertEqual(written["build_node_wire_proxy"], "true")
        self.assertIn(f"m8flow/m8flow-node-wire-proxy sha-{self.TIP}", written["sources"])

    def test_a_missing_image_below_the_tip_stops_the_release(self):
        """This run can only build the commit it runs on."""
        rc, output, _ = self.check(self.BOTH[:1], COMMIT=self.OLD)
        self.assertEqual(rc, 1, output)
        self.assertIn("m8flow-node-wire-proxy", output)

    def test_ga_never_builds(self):
        rc, output, _ = self.check([], CHANNEL="ga", COMMIT=self.TIP)
        self.assertEqual(rc, 1, output)
        self.assertIn("published candidate", output)
        self.assertNotIn("build_backend=true", output)

    def test_every_missing_image_is_reported_at_once(self):
        rc, output, _ = self.check([], COMMIT=self.OLD)
        self.assertEqual(rc, 1, output)
        self.assertIn("m8flow-backend", output)
        self.assertIn("m8flow-node-wire-proxy", output)

    def test_an_image_whose_ci_is_still_running_is_not_built_again(self):
        """Building it here would build that commit twice and race the CI push."""
        rc, output, written = self.check(self.BOTH[:1], FAKE_GH_OUTPUT="1")
        self.assertEqual(rc, 1, output)
        self.assertIn("still running", output)
        self.assertNotEqual(written.get("build_node_wire_proxy"), "true")

    def test_the_check_asks_about_the_components_own_workflow_and_commit(self):
        self.check(self.BOTH[:1])
        calls = gh_calls(self.gh_log)
        self.assertEqual(len(calls), 1, calls)
        args = calls[0]
        self.assertEqual(args[:2], ["run", "list"])
        self.assertEqual(args[args.index("--workflow") + 1], "node-wire-proxy-cicd.yaml")
        self.assertEqual(args[args.index("--commit") + 1], self.OLD)

    def test_an_unanswered_question_stops_rather_than_builds(self):
        rc, output, written = self.check(self.BOTH[:1], FAKE_GH_FAILS="1")
        self.assertEqual(rc, 1, output)
        self.assertIn("Could not ask GitHub", output)
        self.assertNotEqual(written.get("build_node_wire_proxy"), "true")

    def test_published_images_and_ga_runs_never_ask(self):
        self.check(self.BOTH)
        self.check([], CHANNEL="ga")
        self.assertEqual(gh_calls(self.gh_log), [])


@unittest.skipIf(BASH is None, "bash is unavailable")
class CheckTheTag(ShellStep):
    """release.yaml, version/Check the tag: nothing is tagged with an empty tag."""

    COMMIT = "f" * 40

    def setUp(self) -> None:
        self.script = extract_run_block("release.yaml", "version", "Check the tag")

    def check(self, channel: str, tag: str, commit: str = COMMIT) -> int:
        rc, _, _ = self.run_step(self.script, {"CHANNEL": channel, "TAG": tag, "COMMIT": commit})
        return rc

    def test_each_channel_accepts_its_own_shape(self):
        self.assertEqual(self.check("rc", "2.0.9-rc"), 0)
        self.assertEqual(self.check("ga", "2.0.0"), 0)

    def test_an_empty_or_wrong_tag_stops_the_run(self):
        for channel, tag in (("rc", ""), ("ga", ""), ("rc", "2.0.9"), ("ga", "2.0.0-rc")):
            with self.subTest(channel=channel, tag=tag):
                self.assertEqual(self.check(channel, tag), 1)

    def test_an_empty_commit_stops_the_run(self):
        self.assertEqual(self.check("rc", "2.0.9-rc", ""), 1)

    def test_everything_that_tags_waits_on_this_job(self):
        source = (WORKFLOWS / "release.yaml").read_text(encoding="utf-8")
        for job in ("promote", "backend", "designer", "keycloak", "node-wire-proxy", "mcp"):
            with self.subTest(job=job):
                self.assertIn("needs.version.result == 'success'", _job_block(source, job, "release.yaml"))


@unittest.skipIf(BASH is None, "bash is unavailable")
class CreateTheReleaseTag(ShellStep):
    """release.yaml, git-tag/Create the release tag.

    The release tag is created by the workflow, annotated and unsigned, at the
    planned candidate commit, and only after approval and image tagging. That
    is the intended trust model (see the release how-to), pinned here.
    """

    COMMIT = "f" * 40

    def setUp(self) -> None:
        self.script = extract_run_block("release.yaml", "git-tag", "Create the release tag")
        self.bin = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.bin, True)
        install_shim(self.bin, "gh", FAKE_GH_LOGGING)
        self.gh_log = os.path.join(self.bin, "gh.log")

    def create(self, **env: str):
        base = {
            "GH_TOKEN": "x", "REPO": "AOT-Technologies/m8flow", "TAG": "2.0.0",
            "RC_TAG": "2.0.8-rc", "COMMIT": self.COMMIT, "TAG_EXISTS": "false",
            "FAKE_GH_LOG": self.gh_log, "FAKE_GH_OUTPUT": "TAGOBJECT",
        }
        return self.run_step(self.script, {**base, **env}, path_prefix=self.bin)

    def test_creates_an_annotated_tag_at_the_candidate_commit(self):
        rc, output, _ = self.create()
        self.assertEqual(rc, 0, output)
        tag_call, ref_call = gh_calls(self.gh_log)
        self.assertEqual(tag_call[1], "repos/AOT-Technologies/m8flow/git/tags")
        for field in ("tag=2.0.0", f"object={self.COMMIT}", "type=commit"):
            self.assertIn(field, tag_call)
        self.assertTrue(any(a.startswith("message=") and "2.0.8-rc" in a for a in tag_call), tag_call)
        self.assertEqual(ref_call[1], "repos/AOT-Technologies/m8flow/git/refs")
        self.assertIn("ref=refs/tags/2.0.0", ref_call)
        self.assertIn("sha=TAGOBJECT", ref_call, "the ref points at the annotated tag object")

    def test_a_rerun_keeps_the_existing_tag(self):
        """The plan already proved an existing tag marks this candidate."""
        rc, output, _ = self.create(TAG_EXISTS="true")
        self.assertEqual(rc, 0, output)
        self.assertEqual(gh_calls(self.gh_log), [])

    def test_a_refused_write_fails_the_job(self):
        """A tag created after the plan (a race) makes the ref write fail."""
        rc, output, _ = self.create(FAKE_GH_FAILS="1")
        self.assertEqual(rc, 1, output)

    def test_it_runs_only_after_approval_and_image_tagging(self):
        source = (WORKFLOWS / "release.yaml").read_text(encoding="utf-8")
        git_tag = _job_block(source, "git-tag", "release.yaml")
        self.assertIn("needs.promote.result == 'success'", git_tag)
        promote = _job_block(source, "promote", "release.yaml")
        self.assertIn("inputs.channel != 'ga' || needs.approve.result == 'success'", promote)
        self.assertIn("environment: release", _job_block(source, "approve", "release.yaml"))


class ReleaseSummaryGating(ShellStep):
    """release.yaml, summary/Report: which job results fail a release."""

    RC = {
        "CHANNEL": "rc",
        "TAG": "2.0.9-rc",
        "RC_TAG": "",
        "COMMIT": "abc1234",
        "R_VERSION": "success",
        "R_BUILDS": "skipped skipped skipped skipped skipped",
        "R_PROMOTE": "success",
        "R_GIT_TAG": "skipped",
        "R_GH_RELEASE": "skipped",
    }
    GA = {
        "CHANNEL": "ga",
        "TAG": "2.0.0",
        "RC_TAG": "2.0.8-rc",
        "R_GIT_TAG": "success",
        "R_GH_RELEASE": "success",
    }

    def setUp(self) -> None:
        self.script = extract_run_block("release.yaml", "summary", "Report")

    def report(self, **overrides: str):
        return self.run_step(self.script, {**self.RC, **overrides})

    def test_a_healthy_rc_that_reused_every_image(self):
        rc, output, _ = self.report()
        self.assertEqual(rc, 0, output)
        self.assertNotIn("::error::", output)

    def test_a_healthy_rc_that_built_a_missing_image(self):
        rc, output, _ = self.report(R_BUILDS="skipped success skipped skipped skipped")
        self.assertEqual(rc, 0, output)

    def test_a_failed_fallback_build_fails_the_release(self):
        for result in ("failure", "cancelled"):
            with self.subTest(build=result):
                rc, output, _ = self.report(R_BUILDS=f"skipped {result} skipped skipped skipped")
                self.assertEqual(rc, 1, output)

    def test_nothing_is_published_unless_every_image_was_tagged(self):
        for channel in (self.RC, {**self.RC, **self.GA}):
            for result in ("failure", "cancelled", "skipped"):
                with self.subTest(channel=channel["CHANNEL"], promote=result):
                    rc, output, _ = self.run_step(self.script, {**channel, "R_PROMOTE": result})
                    self.assertEqual(rc, 1, output)
                    self.assertIn("::error::", output)

    def test_a_healthy_ga_names_the_candidate_it_shipped(self):
        rc, output, _ = self.report(**self.GA)
        self.assertEqual(rc, 0, output)
        self.assertIn("2.0.0", output)
        self.assertIn("2.0.8-rc", output)
        self.assertIn("abc1234", output)

    def test_a_ga_without_its_git_tag_or_github_release_fails(self):
        for key in ("R_GIT_TAG", "R_GH_RELEASE"):
            for result in ("failure", "skipped"):
                with self.subTest(job=key, result=result):
                    rc, output, _ = self.report(**{**self.GA, key: result})
                    self.assertEqual(rc, 1, output)

    def test_nothing_resolved(self):
        rc, output, _ = self.report(R_VERSION="skipped", TAG="", R_PROMOTE="skipped")
        self.assertEqual(rc, 1, output)
        self.assertIn("no image was tagged", output)

    def test_summary_reads_the_version_job_not_the_tag_job(self):
        """Gating on the rc-only `tag` job would fail every GA release."""
        source = (WORKFLOWS / "release.yaml").read_text(encoding="utf-8")
        self.assertIn("R_VERSION: ${{ needs.version.result }}", source)
        self.assertNotIn("${{ needs.tag.result }}", self.script)


class BuildOnce(unittest.TestCase):
    """The component callers publish one image per main commit, and a release
    finds it by the same paths that decide whether a merge builds."""

    CALLERS = {
        "backend": "backend-cicd.yaml",
        "designer": "designer-cicd.yaml",
        "keycloak": "keycloak-cicd.yaml",
        "node-wire-proxy": "node-wire-proxy-cicd.yaml",
        "mcp": "mcp-server-cicd.yaml",
    }

    def test_main_publishes_sha_tags_and_nothing_else_publishes(self):
        for component, caller in self.CALLERS.items():
            with self.subTest(component=component):
                ci = _job_block((WORKFLOWS / caller).read_text(encoding="utf-8"), "ci", caller)
                self.assertIn(
                    "push: ${{ github.event_name == 'push' && github.ref == 'refs/heads/main' }}", ci
                )
                self.assertIn("format('sha-{0}', github.sha)", ci)

    def test_the_release_reads_every_callers_push_paths(self):
        source = (WORKFLOWS / "release.yaml").read_text(encoding="utf-8")
        for component, caller in self.CALLERS.items():
            with self.subTest(component=component):
                self.assertIn(f".github/workflows/{caller}", source)
        self.assertIn("yq -r '.on.push.paths[]'", source)

    def test_fallback_builds_tag_the_commit_they_build(self):
        source = (WORKFLOWS / "release.yaml").read_text(encoding="utf-8")
        for job in ("backend", "designer", "keycloak", "node-wire-proxy", "mcp"):
            with self.subTest(job=job):
                block = _job_block(source, job, "release.yaml")
                self.assertIn("image_tag: sha-${{ github.sha }}", block)
                self.assertIn(f"build_{job.replace('-', '_')} == 'true'", block)


class ReleaseDocumentation(unittest.TestCase):
    """What the docs say about releasing must match what the workflows do."""

    def test_no_document_mentions_a_ga_suffix(self):
        for path in (
            WORKFLOWS / "README.md",
            WORKFLOWS / "release.yaml",
            WORKFLOWS / "github-release.yml",
            ROOT / "docs" / "how-to" / "release-and-roll-back.md",
        ):
            with self.subTest(path=path.name):
                self.assertNotRegex(path.read_text(encoding="utf-8"), r"-ga\b")

    def test_the_release_how_to_describes_build_once(self):
        """The how-to owns the release flow; the workflows README links to it."""
        readme = (WORKFLOWS / "README.md").read_text(encoding="utf-8")
        how_to = (ROOT / "docs" / "how-to" / "release-and-roll-back.md").read_text(encoding="utf-8")
        for text in ("sha-<commit>", "rc_tag", "## Which image a candidate ships"):
            self.assertIn(text.lstrip("# "), how_to)
        self.assertIn("docs/how-to/release-and-roll-back.md", readme)


class GitHubReleaseInput(ShellStep):
    """github-release.yml: a GitHub Release is cut for a plain X.Y.Z tag only."""

    def setUp(self) -> None:
        self.script = extract_run_block("github-release.yml", "build", "Validate version")

    def test_accepts_a_plain_version(self):
        rc, output, written = self.run_step(self.script, {"VERSION": "2.0.0"})
        self.assertEqual(rc, 0, output)
        self.assertEqual(written.get("RELEASE_VERSION"), "2.0.0")

    def test_rejects_a_candidate_or_a_suffixed_tag(self):
        for rejected in ("2.0.0-rc", "2.0.0-ga", "v2.0.0", "2.0", "2.0.0.1", ""):
            with self.subTest(version=rejected):
                rc, output, _ = self.run_step(self.script, {"VERSION": rejected})
                self.assertEqual(rc, 1, output)

    def test_the_release_is_built_from_the_tag_it_was_given(self):
        source = (WORKFLOWS / "github-release.yml").read_text(encoding="utf-8")
        self.assertIn('git archive --format=tar.gz --prefix="${name}/"', source)
        self.assertIn('"refs/tags/${RELEASE_VERSION}"', source)
        self.assertIn('gh release create "${RELEASE_VERSION}"', source)
        self.assertIn('set-version.py --check "$RELEASE_VERSION"', source)
        self.assertIn('name="m8flow-${RELEASE_VERSION}"', source)

    def test_the_two_workflows_agree_on_what_a_ga_tag_looks_like(self):
        """Both gate on the same shape; a change to one must change the other."""
        shape = r"\^\[0-9\]\+\\\.\[0-9\]\+\\\.\[0-9\]\+\$"
        release = extract_run_block("release.yaml", "branch", "Release channel")
        self.assertRegex(release, shape)
        self.assertRegex(self.script, shape)

    def test_release_yaml_can_call_it(self):
        source = (WORKFLOWS / "github-release.yml").read_text(encoding="utf-8")
        self.assertIn("workflow_call:", source)


class GitHubReleaseCandidate(GitRepoStep):
    """github-release.yml, build/Verify the tag marks a candidate."""

    def setUp(self) -> None:
        super().setUp()
        self.script = extract_run_block("github-release.yml", "build", "Verify the tag marks a candidate")

    def test_a_tag_on_a_candidates_commit_is_accepted(self):
        self.git("checkout", "-q", "--detach", self.m2)
        rc, output, _ = self.run_in_repo(self.script, {"RELEASE_VERSION": "2.0.0"})
        self.assertEqual(rc, 0, output)
        self.assertIn("2.0.8-rc", output)

    def test_a_tag_anywhere_else_is_refused(self):
        self.git("checkout", "-q", "--detach", self.m3)
        rc, output, _ = self.run_in_repo(self.script, {"RELEASE_VERSION": "2.0.0"})
        self.assertEqual(rc, 1, output)
        self.assertIn("release candidate", output)


if __name__ == "__main__":
    unittest.main()
