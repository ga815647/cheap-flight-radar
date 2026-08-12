from datetime import datetime, timezone
from pathlib import Path
import unittest

from cheap_flight_radar.public_intelligence import load_fixed_watch_registry
from cheap_flight_radar.public_sources import parse_source_html


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/public_sources"
UTC = timezone.utc


class PublicSourceParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        watches = load_fixed_watch_registry(ROOT / "flight-radar.yaml")
        cls.by_id = {watch.id: watch for watch in watches}
        cls.observed_at = datetime(2026, 8, 13, 0, 0, tzinfo=UTC)

    def parse_fixture(self, source_id):
        html = (FIXTURES / f"{source_id}.html").read_text(encoding="utf-8")
        watch = self.by_id[source_id]
        return parse_source_html(watch, html, watch.entry_url, self.observed_at)

    def test_active_registry_contains_only_supported_china_airlines_parser(self):
        self.assertEqual(set(self.by_id), {"china_airlines_official"})

    def test_china_airlines_fixture_extracts_live_route_price_contract(self):
        items = self.parse_fixture("china_airlines_official")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].source_id, "china_airlines_official")
        self.assertIn("TPE NRT", items[0].title)
        self.assertEqual(items[0].carrier, "China Airlines")
        self.assertEqual(items[0].price_text, "TWD 10,848")

    def test_china_airlines_generic_ticket_and_disruption_links_are_not_promotions(self):
        html = """
        <html><body>
          <a href='/tw/zh/itinerary-booking/ticket-information/fare-family'>票價產品介紹</a>
          <a href='/tw/zh/prepare-for-the-fly/information/announcements?id=1'>受颱風影響機票處理辦法</a>
          <a href='/tw/zh/itinerary-booking/exclusive-offers/latest-events/student-sale'>學生暑期同行 1+1 優惠</a>
        </body></html>
        """
        watch = self.by_id["china_airlines_official"]
        items = parse_source_html(watch, html, watch.entry_url, self.observed_at)
        self.assertEqual(len(items), 1)
        self.assertIn("學生", items[0].title)


if __name__ == "__main__":
    unittest.main()
