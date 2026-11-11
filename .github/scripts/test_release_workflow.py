"""Behaviour tests for the release workflows' own shell logic.

These run the real `run:` blocks out of the workflow files, so the gating a
release depends on is exercised rather than described. They cover the parts
that are easy to get wrong and expensive to find out about at release time:

* the summary job must not fail a healthy GA run, where `tag` is skipped by
  design and `ga-tag` is what resolves the version;
* the summary job must still hold an rc run to every selected component;
* the version inputs must accept exactly one shape per channel.

The blocks are extracted textually rather than with a YAML parser, because the
runner that executes these tests (check-migrations.yml) installs no packages.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
BASH = shutil.which("bash")


def extract_run_block(workflow: str, step_name: str) -> str:
    """Return the `run:` script of the named step, dedented."""
    source = (WORKFLOWS / workflow).read_text(encoding="utf-8")
    start = source.index(f"- name: {step_name}\n")
    run = re.search(r"(?m)^(\s*)run: \|-?\n", source[start:])
    if run is None:
        raise AssertionError(f"{workflow}: step {step_name!r} has no 'run:' block")
    indent = len(run.group(1))
    body = source[start + run.end():]

    lines: list[str] = []
    for line in body.split("\n"):
        if line.strip() and len(line) - len(line.lstrip()) <= indent:
            break
        lines.append(line)
    script = textwrap.dedent("\n".join(lines))

    # A GitHub expression would be interpolated before the runner ever saw the
    # script, so a block containing one cannot be tested as written.
    assert "${{" not in script, f"{workflow}: step {step_name!r} interpolates an expression"
    return script


@unittest.skipIf(BASH is None, "bash is unavailable")
class ShellStep(unittest.TestCase):
    def run_step(self, script: str, env: dict[str, str]) -> tuple[int, str, dict[str, str]]:
        """Run a step's script with GitHub's files wired up. Returns (rc, output, env-file)."""
        with tempfile.TemporaryDirectory() as tmp:
            paths = {name: os.path.join(tmp, name) for name in ("summary", "env", "output")}
            for path in paths.values():
                open(path, "w").close()
            script_path = os.path.join(tmp, "step.sh")
            with open(script_path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(script)

            proc = subprocess.run(
                [BASH, script_path],
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "GITHUB_STEP_SUMMARY": paths["summary"],
                    "GITHUB_ENV": paths["env"],
                    "GITHUB_OUTPUT": paths["output"],
                    **env,
                },
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
    """release.yaml, 'Report': which job results fail a release."""

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

    def setUp(self) -> None:
        self.script = extract_run_block("release.yaml", "Report")

    def report(self, **overrides: str) -> tuple[int, str, dict[str, str]]:
        return self.run_step(self.script, {**self.SUCCEEDED, **overrides})

    def test_ga_run_succeeds_although_the_tag_job_was_skipped(self):
        """A GA release skips `tag`; only `version` and `promote` must succeed."""
        rc, output, _ = self.report(
            CHANNEL="ga", TAG="2.0.7-ga", RC_TAG="2.0.7-rc",
            R_PROMOTE="success",
            # Every build job is skipped on the GA path.
            R_BACKEND="skipped", R_DESIGNER="skipped", R_KEYCLOAK="skipped",
            R_NODEWIRE="skipped", R_MCP="skipped",
        )
        self.assertEqual(rc, 0, output)
        self.assertIn("2.0.7-ga", output)
        self.assertNotIn("::error::", output)

    def test_rc_run_succeeds_without_the_promote_job(self):
        rc, output, _ = self.report()
        self.assertEqual(rc, 0, output)
        self.assertNotIn("::error::", output)

    def test_ga_run_fails_when_promotion_fails(self):
        rc, output, _ = self.report(
            CHANNEL="ga", TAG="2.0.7-ga", RC_TAG="2.0.7-rc", R_PROMOTE="failure",
        )
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
    """release.yaml, 'Release channel': which tag_name each channel accepts."""

    def setUp(self) -> None:
        self.script = extract_run_block("release.yaml", "Release channel")

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

    def test_the_candidate_tag_is_derived_from_the_ga_tag(self):
        rc, output, _ = self.run_step('echo "${TAG%-ga}-rc"', {"TAG": "2.0.7-ga"})
        self.assertEqual(rc, 0, output)
        self.assertIn("2.0.7-rc", output)


class GitHubReleaseInput(ShellStep):
    """github-release.yml: a GitHub Release is cut for the -ga tag only."""

    def setUp(self) -> None:
        self.script = extract_run_block("github-release.yml", "Validate version")

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
