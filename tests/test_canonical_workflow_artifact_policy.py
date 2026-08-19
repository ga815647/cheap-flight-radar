from pathlib import Path
import unittest


class CanonicalWorkflowArtifactPolicyTest(unittest.TestCase):
    def test_actions_artifacts_are_failure_only_best_effort_debug(self):
        text = Path(".github/workflows/canonical-production-radar.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("Upload failure debug evidence (best effort)", text)
        self.assertIn("if: failure() && steps.request.outputs.active == 'true'", text)
        self.assertIn("continue-on-error: true", text)
        self.assertIn("retention-days: 2", text)
        self.assertNotIn("            _out/", text)
        self.assertNotIn("retention-days: 14", text)

    def test_durable_success_evidence_is_pushed_before_any_debug_upload(self):
        text = Path(".github/workflows/canonical-production-radar.yml").read_text(
            encoding="utf-8"
        )
        self.assertLess(
            text.index("Stage immutable success and recovery evidence"),
            text.index("Upload failure debug evidence (best effort)"),
        )
        self.assertIn("git add data/price-history data/run-evidence", text)
        self.assertIn("git push origin HEAD:history/price-observations", text)


if __name__ == "__main__":
    unittest.main()
