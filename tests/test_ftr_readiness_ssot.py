from pathlib import Path
import unittest


class FTRReadinessSSOTTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        text = Path("flight-radar.yaml").read_text(encoding="utf-8")
        cls.ftr = text.split("ftr_handoff:\n", 1)[1]

    def test_rp08_readiness_is_converged(self):
        self.assertIn("  status: canonical_runtime_active_launch_ready\n", self.ftr)
        self.assertIn("      final_ftr_readiness: true\n", self.ftr)
        self.assertIn("      pending_packages: []\n", self.ftr)
        self.assertNotIn("      final_ftr_readiness: false\n", self.ftr)
        self.assertNotIn("      - RP-08\n", self.ftr)

    def test_recovery_live_proof_remains_not_exercised(self):
        marker = "not_exercised_no_eligible_repair_incident"
        self.assertIn(f"    live_proof_status: {marker}\n", self.ftr)
        self.assertIn(f"      live_recovery_proof_status: {marker}\n", self.ftr)
        self.assertIn("      recovery_live_proof_complete: false\n", self.ftr)
        self.assertNotIn("      recovery_live_proof_complete: true\n", self.ftr)


if __name__ == "__main__":
    unittest.main()
