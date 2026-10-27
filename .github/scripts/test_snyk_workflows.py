"""Policy checks for the supplemental Snyk image scan workflows."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"


class SnykWorkflowPolicy(unittest.TestCase):
    def test_component_ci_uses_current_devx_scanning(self):
        for filename in (
            "backend-cicd.yaml",
            "designer-cicd.yaml",
            "keycloak-cicd.yaml",
            "mcp-server-cicd.yaml",
            "node-wire-proxy-cicd.yaml",
        ):
            with self.subTest(workflow=filename):
                source = (WORKFLOWS / filename).read_text(encoding="utf-8")
                self.assertIn("ci-orchestrator.yaml@8c34de8ae4f1df16c8bfa0ba484a33982d29a4ed", source)
                self.assertIn("config_path:", source)
                self.assertNotIn("snyk-connector-proxy", source)

    def test_current_release_and_notifications_are_present(self):
        release = (WORKFLOWS / "release.yaml").read_text(encoding="utf-8")
        self.assertIn("notify-google-chat.yaml", release)
        self.assertIn("docker.io/m8flow", release)

        for path in (
            "m8flow-backend/devx-ci.yaml",
            "m8flow-designer/devx-ci.yaml",
            "keycloak-extensions/devx-ci.yaml",
            "m8flow-node-wire-proxy/devx-ci.yaml",
            "m8flow-mcp/devx-ci.yaml",
        ):
            source = (ROOT / path).read_text(encoding="utf-8")
            self.assertRegex(source, r"(?m)^notifications:\s*\n\s+enabled: true$")

    def test_snyk_scans_follow_current_registry_and_components(self):
        source = (WORKFLOWS / "snyk-compose-images.yaml").read_text(encoding="utf-8")
        self.assertIn("  release:\n    types: [published]", source)
        self.assertIn("  workflow_dispatch:", source)
        self.assertIn("      component:", source)
        self.assertIn("          - all", source)
        self.assertNotIn("inputs.component == matrix.component", source)
        self.assertIn("github.event_name != 'workflow_dispatch'", source)
        self.assertIn("image_source: public", source)
        self.assertIn("docker.io/m8flow/m8flow-backend:", source)
        self.assertNotIn("653405621825.dkr.ecr", source)
        self.assertNotIn("m8flow-connector-proxy", source)
        for component in (
            "m8flow-backend",
            "m8flow-designer",
            "m8flow-keycloak",
            "m8flow-node-wire-proxy",
            "m8flow-mcp",
        ):
            self.assertIn(f"component: {component}", source)
            self.assertIn(f"name: Scan {component}", source)
        self.assertRegex(source, r"(?m)^\s+- component: supplementary-")

    def test_snyk_reusable_workflow_keeps_report_validation(self):
        source = (WORKFLOWS / "snyk-container-scan.yaml").read_text(encoding="utf-8")
        self.assertIn("SNYK_TOKEN:", source)
        self.assertIn("inputs.image_source == 'public'", source)
        self.assertIn("steps.eligibility.outputs.scan_status != 'skipped_fork_pr'", source)
        self.assertIn("validate_snyk_artifact.py", source)
        self.assertIn("if-no-files-found: error", source)
        self.assertIn("snyk", source.lower())

    def test_scan_matrix_has_no_removed_component_paths(self):
        source = (WORKFLOWS / "snyk-compose-images.yaml").read_text(encoding="utf-8")
        paths = re.findall(r"(?m)^\s+dockerfile: (.+)$", source)
        for dockerfile in paths:
            if "${{" not in dockerfile:
                self.assertTrue((ROOT / dockerfile.strip('"')).exists(), dockerfile)


if __name__ == "__main__":
    unittest.main()
