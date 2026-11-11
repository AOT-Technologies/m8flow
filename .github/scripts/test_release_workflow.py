"""Behaviour tests for the release workflows' own shell logic.

These run the real `run:` blocks out of the workflow files, so the gating a
release depends on is exercised rather than described. They cover the parts
that are easy to get wrong and expensive to find out about at release time:

* the summary job must not fail a healthy GA run, where `tag` is skipped by
  design and `ga-tag` is what resolves the version;
* the summary job must still hold an rc run to every selected component;
* a GA tag must sit on its candidate's commit or a descendant of it;
* the version inputs must accept exactly one shape per channel.

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
JQ = shutil.which("jq")


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
            ("release.yaml", "ga-tag", "Verify tag"),
            ("github-release.yml", "build", "Validate version"),
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
                for line in Path(paths[name]).read_text(encoding="utf-8").splitlines():
                    if "=" in line:
                        key, _, value = line.partition("=")
                        written[key] = value
            output = proc.stdout + proc.stderr + Path(paths["summary"]).read_text(encoding="utf-8")
            return proc.returncode, output, written


class ReleaseSummaryGating(ShellStep):
    """release.yaml, summary/Report: which job results fail a release."""

    SUCCEEDED = {
        "R_VERSION": "success",
        "R_BACKEND": "success",
        "R_DESIGNER": "success",
        "R_KEYCLOAK": "success",
        "R_NODEWIRE": "success",
        "R_MCP": "success",
        "R_PROMOTE": "skipped",
        "TAG": "2.0.7-rc",
        "RC_TAG": "",
        "COMMIT": "abc1234",
        "COMPONENTS": "all",
        "REGISTRY": "docker.io/m8flow",
        "CHANNEL": "rc",
    }
    GA = {
        "CHANNEL": "ga",
        "TAG": "2.0.7-ga",
        "RC_TAG": "2.0.7-rc",
        "R_BACKEND": "skipped",
        "R_DESIGNER": "skipped",
        "R_KEYCLOAK": "skipped",
        "R_NODEWIRE": "skipped",
        "R_MCP": "skipped",
    }

    def setUp(self) -> None:
        self.script = extract_run_block("release.yaml", "summary", "Report")

    def report(self, **overrides: str):
        return self.run_step(self.script, {**self.SUCCEEDED, **overrides})

    def test_ga_run_succeeds_although_the_tag_job_was_skipped(self):
        """A GA release skips `tag`; only `version` and `promote` must succeed."""
        rc, output, _ = self.report(**self.GA, R_PROMOTE="success")
        self.assertEqual(rc, 0, output)
        self.assertIn("2.0.7-ga", output)
        self.assertNotIn("::error::", output)

    def test_rc_run_succeeds_without_the_promote_job(self):
        rc, output, _ = self.report()
        self.assertEqual(rc, 0, output)
        self.assertNotIn("::error::", output)

    def test_a_ga_run_publishes_nothing_unless_promotion_succeeded(self):
        """Any non-success is a failed release: cancelled and skipped included."""
        for result in ("failure", "cancelled", "skipped"):
            with self.subTest(promote=result):
                rc, output, _ = self.report(**self.GA, R_PROMOTE=result)
                self.assertEqual(rc, 1, output)
                self.assertIn("::error::", output)
                self.assertIn("2.0.7-rc", output)

    def test_ga_run_fails_when_the_signed_tag_is_not_verified(self):
        rc, output, _ = self.report(
            CHANNEL="ga", TAG="", RC_TAG="", R_VERSION="skipped", R_PROMOTE="skipped",
        )
        self.assertEqual(rc, 1, output)
        self.assertIn("nothing was promoted", output)

    def test_rc_run_fails_when_the_tag_was_not_cut(self):
        rc, output, _ = self.report(R_VERSION="failure")
        self.assertEqual(rc, 1, output)
        self.assertIn("nothing was built", output)

    def test_rc_run_fails_when_a_selected_component_did_not_build(self):
        rc, output, _ = self.report(R_DESIGNER="failure")
        self.assertEqual(rc, 1, output)
        self.assertIn("designer", output)

    def test_rc_run_ignores_components_that_were_not_selected(self):
        rc, output, _ = self.report(
            COMPONENTS="backend",
            R_DESIGNER="skipped", R_KEYCLOAK="skipped",
            R_NODEWIRE="skipped", R_MCP="skipped",
        )
        self.assertEqual(rc, 0, output)

    def test_summary_reads_the_version_job_not_the_tag_job(self):
        """Guards the rename: gating on `tag` would fail every GA release."""
        source = (WORKFLOWS / "release.yaml").read_text(encoding="utf-8")
        self.assertIn("R_VERSION: ${{ needs.version.result }}", source)
        self.assertNotIn("${{ needs.tag.result }}", self.script)


class GaTagInput(ShellStep):
    """release.yaml, branch/Release channel: which tag_name each channel takes."""

    def setUp(self) -> None:
        self.script = extract_run_block("release.yaml", "branch", "Release channel")

    def check(self, channel: str, tag_name: str) -> int:
        rc, _, _ = self.run_step(self.script, {"CHANNEL": channel, "TAG_NAME": tag_name})
        return rc

    def test_ga_requires_a_ga_tag(self):
        self.assertEqual(self.check("ga", "2.0.7-ga"), 0)
        for rejected in ("2.0.7", "2.0.7-rc", "v2.0.7-ga", "2.0.7-GA", ""):
            with self.subTest(tag_name=rejected):
                self.assertEqual(self.check("ga", rejected), 1)

    def test_rc_refuses_a_final_tag(self):
        self.assertEqual(self.check("rc", "2.1.0-rc"), 0)
        self.assertEqual(self.check("rc", ""), 0, "empty means auto-increment")
        for rejected in ("2.0.7", "2.0.7-ga"):
            with self.subTest(tag_name=rejected):
                self.assertEqual(self.check("rc", rejected), 1)


# A stand-in for `gh api`, dispatching on the URL the step asks for. It serves
# the four calls the GA tag check makes, so the real control flow runs.
FAKE_GH = '''\
import json, os, sys
args = sys.argv[1:]
path = args[1]
expr = args[args.index("--jq") + 1] if "--jq" in args else None
env = os.environ

def emit(obj):
    if expr:
        value = obj
        for part in expr.lstrip(".").split("."):
            value = value[part]
        print(json.dumps(value).strip('"') if not isinstance(value, bool) else str(value).lower())
    else:
        print(json.dumps(obj))

if "/compare/" in path:
    if env.get("FAKE_COMPARE_FAILS") == "1":
        sys.exit(1)
    emit({"status": env["FAKE_STATUS"]})
elif "/git/ref/tags/" in path:
    tag = path.rsplit("/", 1)[-1]
    if tag.endswith("-ga"):
        emit({"object": {"type": env.get("FAKE_GA_TAG_TYPE", "tag"), "sha": "GATAGOBJ"}})
    else:
        if env.get("FAKE_RC_EXISTS", "1") != "1":
            sys.exit(1)
        emit({"object": {"type": "commit", "sha": env["FAKE_RC_SHA"]}})
elif "/git/tags/" in path:
    emit({
        "verification": {
            "verified": env.get("FAKE_VERIFIED", "1") == "1",
            "reason": "unsigned",
        },
        "object": {"sha": env["FAKE_COMMIT"]},
        "tagger": {"name": "Release Tester"},
    })
else:
    sys.exit(f"fake gh: unexpected path {path}")
'''

# Only used where jq is absent (Windows dev machines); CI runners have the real
# one. It covers the plain dot-paths this step reads, nothing more.
FAKE_JQ = '''\
import json, sys
expr = [a for a in sys.argv[1:] if not a.startswith("-")][0]
value = json.load(sys.stdin)
for part in expr.lstrip(".").split("."):
    value = value[part]
print(str(value).lower() if isinstance(value, bool) else value)
'''


@unittest.skipIf(BASH is None, "bash is unavailable")
class GaTagAncestry(ShellStep):
    """release.yaml, ga-tag/Verify tag: which commit a GA tag may mark.

    `gh` is replaced by a stand-in so the step's real control flow runs. Where
    the machine has no `jq`, a shim covering the dot-paths this step reads is
    supplied too; CI runners use the real one.
    """

    COMMIT = "f" * 40
    RC_SHA = "a" * 40

    def setUp(self) -> None:
        self.script = extract_run_block("release.yaml", "ga-tag", "Verify tag")
        self.bin = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.bin, True)
        self._install("gh", FAKE_GH)
        if JQ is None:
            self._install("jq", FAKE_JQ)

    def _install(self, name: str, body: str) -> None:
        """Write an executable shim that bash will find on PATH."""
        py = os.path.join(self.bin, f"{name}_impl.py")
        with open(py, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(body)
        launcher = os.path.join(self.bin, name)
        with open(launcher, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(f'#!/bin/sh\nexec "{sys.executable}" "{py}" "$@"\n')
        os.chmod(launcher, 0o755)

    def verify(self, **overrides: str):
        env = {
            "GH_TOKEN": "x",
            "REPO": "AOT-Technologies/m8flow",
            "TAG": "2.0.7-ga",
            "FAKE_COMMIT": self.COMMIT,
            "FAKE_RC_SHA": self.RC_SHA,
            "FAKE_STATUS": "identical",
            **overrides,
        }
        return self.run_step(self.script, env, path_prefix=self.bin)

    def test_a_tag_on_the_candidate_commit_is_accepted(self):
        rc, output, written = self.verify(FAKE_STATUS="identical")
        self.assertEqual(rc, 0, output)
        self.assertEqual(written.get("rc_tag"), "2.0.7-rc")
        self.assertEqual(written.get("tag"), "2.0.7-ga")
        self.assertEqual(written.get("commit"), self.COMMIT)

    def test_a_tag_on_the_release_metadata_commit_is_accepted(self):
        """set-version.py and the CHANGELOG land after the candidate is cut."""
        rc, output, written = self.verify(FAKE_STATUS="ahead")
        self.assertEqual(rc, 0, output)
        self.assertEqual(written.get("rc_tag"), "2.0.7-rc")

    def test_a_tag_that_predates_or_leaves_the_candidate_is_refused(self):
        for status in ("behind", "diverged"):
            with self.subTest(status=status):
                rc, output, _ = self.verify(FAKE_STATUS=status)
                self.assertEqual(rc, 1, output)
                self.assertIn("::error::", output)
                self.assertIn(status, output)
                self.assertIn("2.0.7-rc", output)

    def test_an_unreadable_comparison_is_refused(self):
        rc, output, _ = self.verify(FAKE_COMPARE_FAILS="1")
        self.assertEqual(rc, 1, output)
        self.assertIn("Could not compare", output)

    def test_a_missing_candidate_tag_is_refused(self):
        rc, output, _ = self.verify(FAKE_RC_EXISTS="0")
        self.assertEqual(rc, 1, output)
        self.assertIn("2.0.7-rc", output)

    def test_an_unsigned_tag_is_refused(self):
        rc, output, _ = self.verify(FAKE_VERIFIED="0")
        self.assertEqual(rc, 1, output)
        self.assertIn("signature", output)

    def test_a_lightweight_tag_is_refused(self):
        rc, output, _ = self.verify(FAKE_GA_TAG_TYPE="commit")
        self.assertEqual(rc, 1, output)
        self.assertIn("lightweight", output)


class GitHubReleaseInput(ShellStep):
    """github-release.yml: a GitHub Release is cut for the -ga tag only."""

    def setUp(self) -> None:
        self.script = extract_run_block("github-release.yml", "build", "Validate version")

    def test_accepts_a_ga_tag_and_derives_the_plain_version(self):
        rc, output, written = self.run_step(self.script, {"VERSION": "2.0.7-ga"})
        self.assertEqual(rc, 0, output)
        self.assertEqual(written.get("RELEASE_TAG"), "2.0.7-ga")
        self.assertEqual(written.get("RELEASE_VERSION"), "2.0.7")
        self.assertEqual(written.get("version"), "2.0.7")

    def test_rejects_anything_that_is_not_a_ga_tag(self):
        for rejected in ("2.0.7", "2.0.7-rc", "v2.0.7-ga", "2.0.7-ga-ga", ""):
            with self.subTest(version=rejected):
                rc, output, _ = self.run_step(self.script, {"VERSION": rejected})
                self.assertEqual(rc, 1, output)

    def test_the_tag_is_used_for_git_and_the_version_for_the_assets(self):
        source = (WORKFLOWS / "github-release.yml").read_text(encoding="utf-8")
        self.assertIn('git archive --format=tar.gz --prefix="${name}/"', source)
        self.assertIn('"refs/tags/${RELEASE_TAG}"', source)
        self.assertIn('gh release create "${RELEASE_TAG}"', source)
        self.assertIn('set-version.py --check "$RELEASE_VERSION"', source)
        self.assertIn('name="m8flow-${RELEASE_VERSION}"', source)


if __name__ == "__main__":
    unittest.main()
