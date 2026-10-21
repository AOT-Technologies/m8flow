"""Regression tests for Snyk workflow policy and report artifacts."""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

from validate_snyk_artifact import validate_artifacts


ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"


def release_snyk_accepted_statuses(source: str | None = None) -> set[str]:
    if source is None:
        source = (WORKFLOWS / "release.yaml").read_text(encoding="utf-8")
    matches = list(
        re.finditer(
            r'for r in "\$S_BACKEND" "\$S_DESIGNER" "\$S_KEYCLOAK" "\$S_NODEWIRE" '
            r'"\$S_PROXY" "\$S_MCP"; do\s+'
            r'if \[\[ "\$r" (.*?)\]\]; then',
            source,
            re.S,
        )
    )
    if len(matches) != 1:
        raise AssertionError(
            f"Expected exactly one release Snyk status allow-list, found {len(matches)}"
        )
    match = matches[0]
    return set(re.findall(r'!= "([^"]+)"', match.group(1)))


def release_component_accepted_statuses() -> set[str]:
    source = (WORKFLOWS / "release.yaml").read_text(encoding="utf-8")
    match = re.search(r'for r in "\$R_BACKEND".*?if \[\[ "\$r" (.*?)\]\]; then', source, re.S)
    if match is None:
        raise AssertionError("Could not find the release component status allow-list")
    return set(re.findall(r'!= "([^"]+)"', match.group(1)))


def snyk_runs_for_event(ci_result: str, event: str, head_repo: str, repository: str) -> bool:
    return ci_result == "success" and (event != "pull_request" or head_repo == repository)


class ReleaseWorkflowPolicy(unittest.TestCase):
    def test_all_container_ci_and_release_paths_run_snyk(self):
        components = {
            "backend": "m8flow-backend",
            "designer": "m8flow-designer",
            "keycloak": "m8flow-keycloak",
            "node-wire-proxy": "m8flow-node-wire-proxy",
            "connector-proxy": "m8flow-connector-proxy",
            "mcp-server": "m8flow-mcp",
        }
        for workflow, component in components.items():
            with self.subTest(workflow=workflow):
                source = (WORKFLOWS / f"{workflow}-cicd.yaml").read_text(encoding="utf-8")
                self.assertIn("uses: ./.github/workflows/snyk-container-scan.yaml", source)
                self.assertIn(f"component: {component}", source)

        release = (WORKFLOWS / "release.yaml").read_text(encoding="utf-8")
        for job in (
            "snyk-backend", "snyk-designer", "snyk-keycloak", "snyk-node-wire-proxy",
            "snyk-connector-proxy", "snyk-mcp",
        ):
            with self.subTest(release_job=job):
                self.assertIn(f"  {job}:", release)
                self.assertIn(job, release.split("  summary:", 1)[1].split("  notify:", 1)[0])

    def test_release_snyk_status_matrix(self):
        accepted = release_snyk_accepted_statuses()
        cases = {
            "component build succeeds + Snyk succeeds": "no_vulnerabilities",
            "component build succeeds + Snyk finds vulnerabilities": "vulnerabilities_found",
            "component build succeeds + no token": "skipped_no_token",
            "component build fails/cancels + Snyk job is skipped": "not_applicable",
        }
        for case, status in cases.items():
            with self.subTest(status=status):
                self.assertIn(status, accepted)
                if case.startswith("component build succeeds"):
                    self.assertIn("success", release_component_accepted_statuses())
        self.assertNotIn("failure", release_component_accepted_statuses())
        self.assertNotIn("cancelled", release_component_accepted_statuses())
        self.assertNotIn("cancelled", accepted)
        self.assertNotIn("scanner_error", accepted)

    def test_reusable_workflow_nonfatal_statuses_match_release_gate(self):
        source = (WORKFLOWS / "snyk-container-scan.yaml").read_text(encoding="utf-8")
        emitted = set(re.findall(r'echo "scan_result=([a-z_]+)"', source))
        self.assertEqual(
            emitted,
            {"no_vulnerabilities", "vulnerabilities_found", "scanner_error", "report_error"},
        )
        accepted = release_snyk_accepted_statuses()
        self.assertTrue({"no_vulnerabilities", "vulnerabilities_found"} <= accepted)
        self.assertFalse({"scanner_error", "report_error"} & accepted)

    def test_build_failure_is_reported_as_build_failure_and_scan_is_not_applicable(self):
        accepted = release_snyk_accepted_statuses()
        self.assertIn("not_applicable", accepted)
        release_source = (WORKFLOWS / "release.yaml").read_text(encoding="utf-8")
        self.assertIn("At least one selected component failed to build", release_source)
        self.assertIn("A Snyk scan failed for a selected image", release_source)
        for build, scan in (
            ("backend", "snyk-backend"),
            ("designer", "snyk-designer"),
            ("keycloak", "snyk-keycloak"),
            ("node-wire-proxy", "snyk-node-wire-proxy"),
        ):
            expected = (
                f"needs.{build}.result != 'success' && 'not_applicable' || "
                f"needs.{scan}.outputs.scan_status || needs.{scan}.result"
            )
            self.assertIn(expected, release_source)

    def test_snyk_allowlist_parser_is_anchored_and_rejects_ambiguity(self):
        source = (WORKFLOWS / "release.yaml").read_text(encoding="utf-8")
        unrelated = 'if [[ "$r" != "vulnerabilities_found" ]]; then'
        self.assertIn("not_applicable", release_snyk_accepted_statuses(source))
        self.assertNotIn("scanner_error", release_snyk_accepted_statuses(source + unrelated))
        with self.assertRaisesRegex(AssertionError, "found 2"):
            release_snyk_accepted_statuses(source + "\n" + source)

    def test_fork_pull_requests_skip_snyk_but_pushes_and_same_repo_prs_run(self):
        component_workflows = (
            "backend-cicd.yaml",
            "designer-cicd.yaml",
            "keycloak-cicd.yaml",
            "node-wire-proxy-cicd.yaml",
            "connector-proxy-cicd.yaml",
            "mcp-server-cicd.yaml",
        )
        guard = "(github.event_name != 'pull_request' || github.event.pull_request.head.repo.full_name == github.repository)"
        for filename in component_workflows:
            with self.subTest(workflow=filename):
                source = (WORKFLOWS / filename).read_text(encoding="utf-8")
                self.assertIn(guard, " ".join(source.split()))
                push_trigger = re.search(r"(?ms)^  push:\n(.*?)(?=^  pull_request:)", source)
                self.assertIsNotNone(push_trigger)
                self.assertIn('- "**"', push_trigger.group(1))
                self.assertIn("github.repository == 'andrepestana-aot/m8flow'", source)
                self.assertIn("Snyk Container Scan", source)

        self.assertFalse(snyk_runs_for_event("success", "pull_request", "fork/repo", "org/repo"))
        self.assertTrue(snyk_runs_for_event("success", "pull_request", "org/repo", "org/repo"))
        self.assertTrue(snyk_runs_for_event("success", "push", "", "org/repo"))
        self.assertFalse(snyk_runs_for_event("failure", "push", "", "org/repo"))


class SnykArtifactValidation(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        root = Path(self.temp_dir.name)
        self.report = root / "report.json"
        self.metadata = root / "metadata.json"
        self.metadata.write_text(json.dumps({"image_ref": "image:tag"}), encoding="utf-8")

    def test_scanned_image_requires_valid_report_and_metadata(self):
        self.report.write_text(json.dumps({"vulnerabilities": []}), encoding="utf-8")
        validate_artifacts(self.report, self.metadata, "no_vulnerabilities")
        validate_artifacts(self.report, self.metadata, "vulnerabilities_found")

    def test_missing_or_invalid_report_fails_completed_scan(self):
        with self.assertRaisesRegex(ValueError, "Snyk report is missing"):
            validate_artifacts(self.report, self.metadata, "vulnerabilities_found")
        self.report.write_text("not json", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Snyk report is not valid JSON"):
            validate_artifacts(self.report, self.metadata, "no_vulnerabilities")

    def test_missing_or_invalid_metadata_always_fails(self):
        with self.assertRaisesRegex(ValueError, "Image metadata is missing"):
            validate_artifacts(self.report, self.metadata.with_name("absent.json"), "skipped_no_token")
        self.metadata.write_text("[]", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Image metadata must contain a JSON object"):
            validate_artifacts(self.report, self.metadata, "skipped_no_token")

    def test_missing_token_allows_metadata_only_artifact(self):
        validate_artifacts(self.report, self.metadata, "skipped_no_token")

    def test_workflow_runs_validator_and_uploads_any_available_artifacts(self):
        source = (WORKFLOWS / "snyk-container-scan.yaml").read_text(encoding="utf-8")
        self.assertIn("python3 .github/scripts/validate_snyk_artifact.py", source)
        self.assertIn("if-no-files-found: error", source)
        self.assertIn("steps.token-check.outputs.scan_status != 'skipped_no_token'", source)
        self.assertIn("snyk-container-${{ inputs.component }}.json", source)
        self.assertIn("snyk-container-${{ inputs.component }}-metadata.json", source)

    def test_reusable_workflow_skips_fork_before_checkout_or_image_access(self):
        source = (WORKFLOWS / "snyk-container-scan.yaml").read_text(encoding="utf-8")
        eligibility = source.index("- name: Check scan eligibility")
        checkout = source.index("- name: Checkout")
        self.assertLess(eligibility, checkout)
        self.assertIn('"$EVENT_NAME" == "pull_request" && "$HEAD_REPOSITORY" != "$BASE_REPOSITORY"', source)
        self.assertIn('echo "scan_status=skipped_fork_pr"', source)
        self.assertIn("steps.eligibility.outputs.scan_status != 'skipped_fork_pr'", source)
        self.assertIn("steps.eligibility.outputs.scan_status || 'not_run'", source)


if __name__ == "__main__":
    unittest.main()
