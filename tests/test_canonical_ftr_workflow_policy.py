from pathlib import Path
import unittest


class CanonicalFTRWorkflowPolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.production = Path(".github/workflows/canonical-production-radar.yml").read_text(encoding="utf-8")
        cls.isolated = Path(".github/workflows/canonical-production-radar-test.yml").read_text(encoding="utf-8")

    def test_producer_sha_is_actual_app_main_checkout_not_trigger_sha(self):
        text = self.production
        self.assertIn("Checkout current application", text)
        self.assertIn("ref: main", text)
        self.assertIn('APP_SHA="$(git -C _app rev-parse HEAD)"', text)
        self.assertIn('--producer-commit-sha "$APP_SHA"', text)
        self.assertNotIn('--producer-commit-sha "${{ github.sha }}"', text)
        self.assertIn('--trigger-sha "${{ github.sha }}"', text)

    def test_cfr_evidence_is_persisted_before_ftr_and_ftr_failure_does_not_skip_cfr_publication(self):
        text = self.production
        self.assertLess(
            text.index("Stage immutable CFR success and recovery evidence"),
            text.index("Stage canonical FTR handoff from durable CFR evidence"),
        )
        self.assertLess(
            text.index("Stage canonical FTR handoff from durable CFR evidence"),
            text.index("Restore publication manifest from durable evidence"),
        )
        self.assertLess(
            text.index("Explicitly dispatch Radar Pages"),
            text.index("Fail after durable canonical FTR failure persistence"),
        )
        self.assertIn("git add data/price-history data/run-evidence", text)
        self.assertIn("git add data/ftr-feed data/run-evidence", text)
        self.assertIn("git push origin HEAD:history/price-observations", text)

    def test_acquisition_and_cfr_stage_failure_get_durable_ftr_failure_state(self):
        text = self.production
        self.assertIn("Persist canonical FTR acquisition/staging failure", text)
        self.assertIn("cheap_flight_radar.canonical_ftr_runtime stage-failure", text)
        self.assertIn("steps.acquisition.outcome == 'failure'", text)
        self.assertIn("steps.success.outcome == 'failure'", text)
        self.assertIn("data/ftr-feed data/run-evidence", text)
        self.assertIn("Fail after durable canonical FTR failure persistence", text)

    def test_artifact_upload_is_after_durable_decision_and_best_effort(self):
        text = self.production
        self.assertLess(
            text.index("Fail after durable canonical FTR failure persistence"),
            text.index("Upload failure debug evidence (best effort)"),
        )
        artifact_tail = text[text.index("Upload failure debug evidence (best effort)"):]
        self.assertIn("continue-on-error: true", artifact_tail)
        self.assertNotIn("data/ftr-feed", artifact_tail)

    def test_isolated_workflow_can_only_push_test_namespaces(self):
        text = self.isolated
        self.assertIn('evidence_ref.startswith("test/radar-evidence/")', text)
        self.assertIn('publication_ref.startswith("test/radar-publication/")', text)
        self.assertIn('git push origin HEAD:"$EVIDENCE_REF"', text)
        self.assertIn('git push origin HEAD:"$PUBLICATION_REF"', text)
        self.assertNotIn("git push origin HEAD:history/price-observations", text)
        self.assertNotIn("git push origin HEAD:publication/radar-reports", text)
        self.assertIn("radar-pages-isolated-test.yml/dispatches", text)
        self.assertNotIn("actions/workflows/radar-pages.yml/dispatches", text)

    def test_isolated_ftr_uses_actual_app_sha_and_artifact_is_optional(self):
        text = self.isolated
        self.assertIn('APP_SHA="$(git -C _app rev-parse HEAD)"', text)
        self.assertIn('--producer-commit-sha "$APP_SHA"', text)
        self.assertIn("Upload isolated failure debug evidence (best effort)", text)
        tail = text[text.index("Upload isolated failure debug evidence (best effort)"):]
        self.assertIn("continue-on-error: true", tail)
        self.assertIn("retention-days: 2", tail)


if __name__ == "__main__":
    unittest.main()
