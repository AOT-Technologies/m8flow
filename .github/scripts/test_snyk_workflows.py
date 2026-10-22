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


def workflow_job_block(source: str, job_name: str) -> str:
    match = re.search(
        rf"(?ms)^  {re.escape(job_name)}:\n(.*?)(?=^  [\w-]+:\n|\Z)",
        source,
    )
    if match is None:
        raise AssertionError(f"Could not find workflow job {job_name!r}")
    return match.group(1)


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
    match = re.search(
        r'for pair in "backend=\$R_BACKEND".*?\[\[ "\$result" == "([^"]+)" \]\] \|\|',
        source,
        re.S,
    )
    if match is None:
        raise AssertionError("Could not find the selected release component success check")
    return {match.group(1)}


class ReleaseWorkflowPolicy(unittest.TestCase):
    def test_application_images_are_scanned_only_in_release_workflow(self):
        scans = (
            ("backend", "snyk-backend", "m8flow-backend"),
            ("designer", "snyk-designer", "m8flow-designer"),
            ("keycloak", "snyk-keycloak", "m8flow-keycloak"),
            ("node-wire-proxy", "snyk-node-wire-proxy", "m8flow-node-wire-proxy"),
            ("connector-proxy", "snyk-connector-proxy", "m8flow-connector-proxy"),
            ("mcp-server", "snyk-mcp", "m8flow-mcp"),
        )
        for workflow, _job, _component in scans:
            with self.subTest(workflow=workflow):
                source = (WORKFLOWS / f"{workflow}-cicd.yaml").read_text(encoding="utf-8")
                self.assertNotIn("uses: ./.github/workflows/snyk-container-scan.yaml", source)
                self.assertNotIn("Snyk Container Scan", source)

        release = (WORKFLOWS / "release.yaml").read_text(encoding="utf-8")
        summary = workflow_job_block(release, "summary")
        for _workflow, job, component in scans:
            with self.subTest(release_job=job):
                job_block = workflow_job_block(release, job)
                self.assertIn("uses: ./.github/workflows/snyk-container-scan.yaml", job_block)
                self.assertIn(f"component: {component}", job_block)
                self.assertRegex(summary, rf"(?m)^\s+needs:.*\b{re.escape(job)}\b")

    def test_compose_third_party_images_are_in_snyk_matrix(self):
        compose_files = list((ROOT / "docker").glob("*compose*.yml"))
        compose_files += list((ROOT / "docker").glob("*compose*.yaml"))
        compose_files += [ROOT / "m8flow-mcp" / "docker-compose.yml"]
        compose_images = set()
        for compose_file in compose_files:
            for image in re.findall(
                r"(?m)^\s*image:\s*([^\s#]+)",
                compose_file.read_text(encoding="utf-8"),
            ):
                if not image.startswith(("m8flow-", "m8flow/")):
                    compose_images.add(image)

        workflow = (WORKFLOWS / "snyk-compose-images.yaml").read_text(encoding="utf-8")
        matrix_images = set(re.findall(r"(?m)^\s+image:\s*([^\s#]+)", workflow))
        matrix_entries = re.findall(
            r"(?ms)^\s+- component:\s*([^\n]+)\n\s+image:\s*([^\s#]+)",
            workflow,
        )
        component_by_image = {image: component for component, image in matrix_entries}
        dockerfiles = (
            ROOT / "docker" / "m8flow.backend.Dockerfile",
            ROOT / "docker" / "m8flow.designer.Dockerfile",
            ROOT / "docker" / "m8flow.frontend.Dockerfile",
            ROOT / "docker" / "m8flow.keycloak.Dockerfile",
            ROOT / "docker" / "m8flow.python-base.Dockerfile",
            ROOT / "m8flow-connector-proxy" / "Dockerfile",
            ROOT / "m8flow-connector-proxy" / "dev.Dockerfile",
            ROOT / "m8flow-node-wire-proxy" / "Dockerfile",
            ROOT / "m8flow-nats-consumer" / "Dockerfile",
            ROOT / "m8flow-mcp" / "Dockerfile",
        )
        dockerfile_bases = set()
        for dockerfile in dockerfiles:
            for image in re.findall(
                r"(?mi)^\s*FROM\s+([^\s]+)",
                dockerfile.read_text(encoding="utf-8"),
            ):
                if "${" in image:
                    continue  # The ARG default is accounted for in the matrix.
                if "/" not in image and ":" not in image:
                    continue  # A named stage, not an external image reference.
                dockerfile_bases.add(image)

        self.assertTrue(compose_images <= matrix_images)
        self.assertLessEqual(dockerfile_bases, matrix_images, dockerfile_bases - matrix_images)
        self.assertTrue(
            all(not component_by_image[image].startswith("supplementary-") for image in compose_images),
            "Compose runtime images must remain in the required baseline",
        )
        dockerfile_only_images = dockerfile_bases - compose_images
        self.assertTrue(
            all(component_by_image[image].startswith("supplementary-") for image in dockerfile_only_images),
            "Dockerfile-only images must be labeled supplementary",
        )

    def test_temporary_snyk_testing_overrides_are_removed(self):
        config_files = (
            "m8flow-backend/devx-ci.yaml",
            "m8flow-designer/devx-ci.yaml",
            "keycloak-extensions/devx-ci.yaml",
            "m8flow-node-wire-proxy/devx-ci.yaml",
            "m8flow-connector-proxy/devx-ci.yaml",
            "m8flow-mcp/devx-ci.yaml",
        )
        for filename in config_files:
            with self.subTest(config=filename):
                source = (ROOT / filename).read_text(encoding="utf-8")
                self.assertRegex(source, r"(?m)^notifications:\s*\n\s+enabled: true$")

        release = (WORKFLOWS / "release.yaml").read_text(encoding="utf-8")
        pr_notification = (WORKFLOWS / "pr-notification.yml").read_text(encoding="utf-8")
        self.assertIn("if: always() && inputs.dry_run != true", release)
        self.assertIn("if: github.event.pull_request.draft == false", pr_notification)
        for filename in (
            "backend-cicd.yaml", "designer-cicd.yaml", "keycloak-cicd.yaml",
            "connector-proxy-cicd.yaml", "node-wire-proxy-cicd.yaml", "mcp-server-cicd.yaml",
        ):
            source = (WORKFLOWS / filename).read_text(encoding="utf-8")
            self.assertNotIn('branches:\n      - "**"', source)
            self.assertIn("branches:\n      - main\n      - refactor/next-gen", source)

        third_party = (WORKFLOWS / "snyk-compose-images.yaml").read_text(encoding="utf-8")
        self.assertIn("on:\n  release:\n    types: [published]\n  workflow_dispatch:", third_party)

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
        self.assertEqual(release_component_accepted_statuses(), {"success"})
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
        self.assertIn("was selected but did not build", release_source)
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

    def test_component_scans_are_absent_from_push_and_pull_request_workflows(self):
        component_workflows = (
            "backend-cicd.yaml",
            "designer-cicd.yaml",
            "keycloak-cicd.yaml",
            "node-wire-proxy-cicd.yaml",
            "connector-proxy-cicd.yaml",
            "mcp-server-cicd.yaml",
        )
        for filename in component_workflows:
            with self.subTest(workflow=filename):
                source = (WORKFLOWS / filename).read_text(encoding="utf-8")
                push_trigger = re.search(r"(?ms)^  push:\n(.*?)(?=^  pull_request:)", source)
                self.assertIsNotNone(push_trigger)
                self.assertIn("- main", push_trigger.group(1))
                self.assertIn("- refactor/next-gen", push_trigger.group(1))
                self.assertNotIn('- "**"', push_trigger.group(1))
                ci_job = source.split("  ci:", 1)[1].split("  cd-dev:", 1)[0]
                self.assertIn("if: github.event_name != 'workflow_dispatch'", ci_job)
                self.assertNotIn("uses: ./.github/workflows/snyk-container-scan.yaml", source)

        release = (WORKFLOWS / "release.yaml").read_text(encoding="utf-8")
        self.assertIn("uses: ./.github/workflows/snyk-container-scan.yaml", release)

    def test_compose_workflow_runs_on_release_or_manual_dispatch(self):
        source = (WORKFLOWS / "snyk-compose-images.yaml").read_text(encoding="utf-8")
        triggers = source.split("permissions:", 1)[0]
        self.assertIn("on:\n  release:\n    types: [published]", triggers)
        self.assertIn("  workflow_dispatch:\n    inputs:\n      release_tag:", triggers)
        self.assertIn("required: true", triggers)
        self.assertNotIn("  push:", triggers)
        self.assertNotIn("  pull_request:", triggers)

        manual_images = source.split("  scan-m8flow-images:", 1)[1].split("  scan:", 1)[0]
        self.assertIn("if: github.event_name == 'workflow_dispatch'", manual_images)
        self.assertIn("image_source: ecr", manual_images)
        self.assertIn("${{ inputs.release_tag }}", manual_images)
        self.assertIn("aws_role_to_assume:", manual_images)
        for image in (
            "m8flow-backend", "m8flow-designer", "m8flow-keycloak",
            "m8flow-connector-proxy", "m8flow-node-wire-proxy", "m8flow-mcp",
        ):
            with self.subTest(image=image):
                self.assertIn(f"image: {image}", manual_images)


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

    def test_reusable_workflow_can_pull_public_images_without_dockerfile(self):
        source = (WORKFLOWS / "snyk-container-scan.yaml").read_text(encoding="utf-8")
        self.assertIn("image_source:", source)
        self.assertIn("inputs.image_source == 'public'", source)
        self.assertIn('docker pull "$IMAGE_URI"', source)
        self.assertIn('if [[ -n "$DOCKERFILE" ]]', source)


if __name__ == "__main__":
    unittest.main()
