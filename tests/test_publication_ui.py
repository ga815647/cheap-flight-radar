from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest

from cheap_flight_radar.publication import build_site


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "publication"
POLICY = ROOT / "flight-radar.yaml"
PAGES_WORKFLOW = ROOT / ".github" / "workflows" / "radar-pages.yml"


class PublicationUiTests(unittest.TestCase):
    def _build_fixture(self, root: Path) -> Path:
        history = root / "history"
        manifests = root / "manifests"
        site = root / "site"
        snapshot = (
            history
            / "data"
            / "price-history"
            / "2026"
            / "08"
            / "12"
            / "corrected-radar-v1-20260812T125139-0800.json"
        )
        snapshot.parent.mkdir(parents=True)
        shutil.copyfile(FIXTURES / "corrected-radar-v1-snapshot.json", snapshot)
        manifests.mkdir(parents=True)
        shutil.copyfile(
            FIXTURES / "corrected-radar-v1-manifest.json",
            manifests / "corrected-radar-v1-20260812T125139-0800.json",
        )
        build_site(
            policy_path=POLICY,
            history_dir=history,
            manifest_dir=manifests,
            site_dir=site,
        )
        return site

    def test_run_page_uses_product_hierarchy_without_external_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            site = self._build_fixture(Path(tmp))
            run_page = next((site / "runs").glob("*/index.html"))
            text = run_page.read_text(encoding="utf-8")

            self.assertIn('class="hero-grid"', text)
            self.assertIn('class="coverage-strip"', text)
            self.assertIn('class="market-grid"', text)
            self.assertIn('class="view-label">Absolute Cheapest', text)
            self.assertIn('class="view-label">Near-Term Cheapest', text)
            self.assertIn('class="view-label">Best Short Break', text)
            self.assertIn('class="view-label">Unusual Long-Haul Deal', text)
            self.assertIn("Sparse history", text)
            self.assertIn("Historical evidence details", text)
            self.assertIn("<summary>Failed / Non-converged Cheap Seeds</summary>", text)
            self.assertIn("<summary>Run Notes</summary>", text)
            self.assertIn("@media(max-width:780px)", text)
            self.assertNotIn("<script", text.lower())
            self.assertNotIn("stylesheet\" href=", text.lower())

    def test_index_is_styled_and_links_latest_and_permanent_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            site = self._build_fixture(Path(tmp))
            text = (site / "index.html").read_text(encoding="utf-8")

            self.assertIn('class="latest-card"', text)
            self.assertIn('class="run-list"', text)
            self.assertIn('href="latest/"', text)
            self.assertIn(
                'href="runs/corrected-radar-v1-20260812T125139-0800/"',
                text,
            )
            self.assertIn("Permanent fare intelligence reports", text)

    def test_latest_remains_byte_identical_to_permanent_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            site = self._build_fixture(Path(tmp))
            run_page = next((site / "runs").glob("*/index.html"))
            self.assertEqual(
                (site / "latest" / "index.html").read_bytes(),
                run_page.read_bytes(),
            )

    def test_pages_rebuilds_for_new_reports_and_main_presentation_changes(self) -> None:
        text = PAGES_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("- publication/radar-reports", text)
        self.assertIn("- main", text)
        self.assertIn('"publication/runs/*.json"', text)
        self.assertIn('"src/cheap_flight_radar/publication.py"', text)
        self.assertIn('"flight-radar.yaml"', text)
        self.assertIn('".github/workflows/radar-pages.yml"', text)
        self.assertNotIn("schedule:", text)


if __name__ == "__main__":
    unittest.main()
