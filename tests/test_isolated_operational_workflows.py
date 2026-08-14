from pathlib import Path
import unittest


class IsolatedOperationalWorkflowTest(unittest.TestCase):
    def test_canonical_test_harness_reuses_production_runtime_but_only_test_refs(self):
        text = Path(".github/workflows/canonical-production-radar-test.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("ops/radar-test-request", text)
        self.assertIn("requests/test-daily.json", text)
        self.assertIn('mode") != "isolated_canonical_test"', text)
        self.assertIn("test/radar-evidence/", text)
        self.assertIn("test/radar-publication/", text)
        self.assertIn("Validate isolated publication/evidence baseline before claim", text)
        self.assertIn("python -m cheap_flight_radar.production_operations inspect", text)
        self.assertIn("python -m cheap_flight_radar.production_operations claim", text)
        self.assertIn("python -m cheap_flight_radar.production_runtime", text)
        self.assertIn("python -m cheap_flight_radar.production_operations stage-success", text)
        self.assertIn("python -m cheap_flight_radar.production_operations restore-publication", text)
        self.assertIn("radar-pages-isolated-test.yml/dispatches", text)
        self.assertLess(
            text.index("Validate isolated publication/evidence baseline before claim"),
            text.index("Inspect isolated daily state"),
        )
        self.assertLess(
            text.index("Validate isolated publication/evidence baseline before claim"),
            text.index("Persist isolated one-attempt acquisition claim"),
        )
        self.assertNotIn("ops/radar-request\n", text)
        self.assertNotIn("HEAD:history/price-observations", text)
        self.assertNotIn("HEAD:publication/radar-reports", text)
        self.assertNotIn("schedule:", text)

    def test_isolated_pages_build_cannot_deploy_live_pages(self):
        text = Path(".github/workflows/radar-pages-isolated-test.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("workflow_dispatch:", text)
        self.assertIn("test/radar-evidence/*", text)
        self.assertIn("test/radar-publication/*", text)
        self.assertIn("python -m cheap_flight_radar.production_publication", text)
        self.assertIn("actions/upload-artifact@v4", text)
        self.assertNotIn("actions/deploy-pages", text)
        self.assertNotIn("pages: write", text)
        self.assertNotIn("publication/radar-reports", text)
        self.assertNotIn("history/price-observations", text)
        self.assertNotIn("schedule:", text)


if __name__ == "__main__":
    unittest.main()
