"""Behaviour tests for the pre-deploy image check (verify-image.yml).

They run the real `Verify image` step with `docker` replaced by a stand-in, and
pin that every component's deploy jobs wait on the check.
"""

from __future__ import annotations

import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_release_workflow import (  # noqa: E402
    BASH,
    FAKE_DOCKER,
    WORKFLOWS,
    ShellStep,
    _job_block,
    extract_run_block,
    install_shim,
)

REPOSITORY = "docker.io/m8flow/m8flow-backend"
DIGEST = "sha256:" + "0" * 64


@unittest.skipIf(BASH is None, "bash is unavailable")
class VerifyImage(ShellStep):
    """verify-image.yml, verify/Verify image: what a deploy may roll out."""

    def setUp(self) -> None:
        self.script = extract_run_block("verify-image.yml", "verify", "Verify image")
        self.bin = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.bin, True)
        install_shim(self.bin, "docker", FAKE_DOCKER)

    def verify(self, image_uri: str, existing: tuple[str, ...] = ()):
        env = {
            "IMAGE_URI": image_uri,
            "REPOSITORY": REPOSITORY,
            "FAKE_EXISTING": " ".join(existing),
        }
        return self.run_step(self.script, env, path_prefix=self.bin)

    def test_a_published_tag_of_this_component_is_accepted(self):
        for tag in ("sha-" + "a" * 40, "2.0.8-rc", "2.0.0"):
            with self.subTest(tag=tag):
                ref = f"{REPOSITORY}:{tag}"
                rc, output, _ = self.verify(ref, (ref,))
                self.assertEqual(rc, 0, output)
                self.assertIn("Deploying", output)

    def test_a_digest_reference_is_accepted(self):
        ref = f"{REPOSITORY}@{DIGEST}"
        rc, output, _ = self.verify(ref, (ref,))
        self.assertEqual(rc, 0, output)

    def test_an_image_that_was_never_published_is_refused(self):
        """A failed, superseded or never-run build: caught before the cluster."""
        rc, output, _ = self.verify(f"{REPOSITORY}:sha-" + "b" * 40)
        self.assertEqual(rc, 1, output)
        self.assertIn("does not exist", output)

    def test_another_components_image_is_refused(self):
        ref = "docker.io/m8flow/m8flow-designer:2.0.0"
        rc, output, _ = self.verify(ref, (ref,))
        self.assertEqual(rc, 1, output)
        self.assertIn("not this component's image", output)

    def test_a_reference_without_the_registry_is_refused(self):
        ref = "m8flow/m8flow-backend:2.0.0"
        rc, output, _ = self.verify(ref, (ref,))
        self.assertEqual(rc, 1, output)
        self.assertIn(REPOSITORY, output)

    def test_a_reference_without_a_tag_is_refused(self):
        for ref in (REPOSITORY, f"{REPOSITORY}:", f"{REPOSITORY}@sha256:abc"):
            with self.subTest(ref=ref):
                rc, output, _ = self.verify(ref, (ref,))
                self.assertEqual(rc, 1, output)

    def test_whitespace_is_refused_not_trimmed(self):
        """The deploy gets the raw string, so the check must not pass a cleaned one."""
        ref = f"{REPOSITORY}:2.0.0"
        for given in (f" {ref}", f"{ref} ", ""):
            with self.subTest(image_uri=given):
                rc, output, _ = self.verify(given, (ref,))
                self.assertEqual(rc, 1, output)


class DeploysWaitForTheCheck(unittest.TestCase):
    """Every deploy job of every component needs the check."""

    CALLERS = {
        "backend-cicd.yaml": "m8flow-backend/devx-ci.yaml",
        "designer-cicd.yaml": "m8flow-designer/devx-ci.yaml",
        "keycloak-cicd.yaml": "keycloak-extensions/devx-ci.yaml",
        "node-wire-proxy-cicd.yaml": "m8flow-node-wire-proxy/devx-ci.yaml",
        "mcp-server-cicd.yaml": "m8flow-mcp/devx-ci.yaml",
    }

    def test_every_deploy_job_needs_verify_image(self):
        for caller, config in self.CALLERS.items():
            source = (WORKFLOWS / caller).read_text(encoding="utf-8")
            check = _job_block(source, "verify-image", caller)
            with self.subTest(caller=caller, job="verify-image"):
                self.assertIn("uses: ./.github/workflows/verify-image.yml", check)
                self.assertIn(f"config_path: {config}", check)
            deploys = re.findall(r"(?m)^  (cd-[\w-]+):$", source)
            self.assertTrue(deploys, caller)
            for job in deploys:
                with self.subTest(caller=caller, job=job):
                    self.assertIn("needs: verify-image", _job_block(source, job, caller))

    def test_the_check_reads_the_same_config_the_build_publishes_from(self):
        for caller, config in self.CALLERS.items():
            ci = _job_block((WORKFLOWS / caller).read_text(encoding="utf-8"), "ci", caller)
            with self.subTest(caller=caller):
                self.assertIn(f"config_path: {config}", ci)


if __name__ == "__main__":
    unittest.main()
