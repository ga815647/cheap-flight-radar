from pathlib import Path
import unittest


class ProductionWorkflowArtifactPolicyTest(unittest.TestCase):
    def _assert_failure_only_debug(self, path, *, upload_name):
        text = Path(path).read_text(encoding="utf-8")
        self.assertIn(upload_name, text)
        self.assertIn("if: failure() && steps.request.outputs.active == 'true'", text)
        self.assertIn("continue-on-error: true", text)
        self.assertIn("retention-days: 2", text)
        self.assertNotIn("            _out/", text)
        self.assertNotIn("retention-days: 14", text)
        return text

    def test_canonical_artifacts_are_failure_only_best_effort_debug(self):
        text = self._assert_failure_only_debug(
            ".github/workflows/canonical-production-radar.yml",
            upload_name="Upload failure debug evidence (best effort)",
        )
        self.assertLess(
            text.index("Stage immutable success and recovery evidence"),
            text.index("Upload failure debug evidence (best effort)"),
        )
        self.assertIn("git add data/price-history data/run-evidence", text)
        self.assertIn("git push origin HEAD:history/price-observations", text)

    def test_operator_artifacts_are_failure_only_best_effort_debug(self):
        text = self._assert_failure_only_debug(
            ".github/workflows/operator-production-radar.yml",
            upload_name="Upload operator failure debug evidence (best effort)",
        )
        self.assertLess(
            text.index("Stage immutable operator success and recovery evidence"),
            text.index("Upload operator failure debug evidence (best effort)"),
        )
        self.assertIn("git add data/price-history data/run-evidence", text)
        self.assertIn("git push origin HEAD:history/price-observations", text)


if __name__ == "__main__":
    unittest.main()
