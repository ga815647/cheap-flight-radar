from datetime import datetime, timezone
from pathlib import Path
import unittest

from cheap_flight_radar.public_intelligence import load_fixed_watch_registry
from cheap_flight_radar.public_sources import ParseContractError, parse_source_html


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/public_sources"
UTC = timezone.utc


class PublicSourceParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        watches = load_fixed_watch_registry(ROOT / "flight-radar.yaml")
        cls.by_id = {watch.id: watch for watch in watches}
        cls.observed_at = datetime(2026, 8, 11, 8, 0, tzinfo=UTC)

    def parse_fixture(self, source_id):
        html = (FIXTURES / f"{source_id}.html").read_text(encoding="utf-8")
        watch = self.by_id[source_id]
        return parse_source_html(watch, html, watch.entry_url, self.observed_at)

    def test_tigerair_fixture_extracts_only_promo_signal(self):
        items = self.parse_fixture("tigerair_tw_official")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].source_id, "tigerair_tw_official")
        self.assertIn("促銷", items[0].title)
        self.assertEqual(items[0].price_text, "NT$1,999")

    def test_china_airlines_fixture_extracts_only_promo_signal(self):
        items = self.parse_fixture("china_airlines_official")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].source_id, "china_airlines_official")
        self.assertIn("優惠", items[0].title)
        self.assertEqual(items[0].carrier, "China Airlines")

    def test_ptt_fixture_keeps_information_airfare_post_only(self):
        items = self.parse_fixture("ptt_japan_travel_info")
        self.assertEqual(len(items), 1)
        self.assertTrue(items[0].title.startswith("[資訊]"))
        self.assertIn("特價", items[0].title)

    def test_parser_drift_is_visible(self):
        with self.assertRaises(ParseContractError):
            parse_source_html(
                self.by_id["ptt_japan_travel_info"],
                "<html><body>layout changed</body></html>",
                self.by_id["ptt_japan_travel_info"].entry_url,
                self.observed_at,
            )


if __name__ == "__main__":
    unittest.main()
