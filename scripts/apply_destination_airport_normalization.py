from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"pattern not found in {path}: {old[:120]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "PRODUCT_INTENT.md",
    "- Compare a destination against its own normal price level rather than comparing unrelated destinations by raw fare alone.\n",
    "- Compare a destination against its own normal price level rather than comparing unrelated destinations by raw fare alone.\n"
    "- The primary airfare-anomaly normalization unit is the **exact destination airport**, pooled across the accepted Taiwan origins TPE, TSA, RMQ, and KHH. The ticket itself always retains its actual origin, but an origin-specific normal price must not make an otherwise ordinary destination look exceptionally cheap when another accepted Taiwan origin has a materially lower normal price to the same destination airport.\n"
    "- For the same destination airport, prefer the **lowest current complete airfare across accepted Taiwan origins** before deciding which concrete origin/date itinerary deserves scarce exact revalidation and publication.\n",
)

replace_once(
    "flight-radar.yaml",
    "ranking:\n  preserve_views:\n",
    "ranking:\n"
    "  destination_airport_anomaly_normalization:\n"
    "    enabled: true\n"
    "    destination_key: exact_destination_airport\n"
    "    taiwan_origin_scope: configured_origin_airports\n"
    "    candidate_current_fare: lowest_complete_airfare_across_configured_taiwan_origins_for_destination\n"
    "    external_typical_baseline: minimum_qualified_typical_price_for_same_destination_airport_across_configured_taiwan_origins_in_current_sweep\n"
    "    exact_itinerary_retains_actual_origin: true\n"
    "    origin_specific_typical_must_not_override_lower_same_destination_baseline: true\n"
    "    city_grouping_role: secondary_presentation\n"
    "  preserve_views:\n",
)

replace_once(
    "flight-radar.yaml",
    "  comparison_dimensions:\n  - exact_route_when_available\n  - trip_type\n  - departure_lead_time_bucket\n",
    "  comparison_origin_airports:\n"
    "  - TPE\n"
    "  - TSA\n"
    "  - RMQ\n"
    "  - KHH\n"
    "  run_level_destination_sample: lowest_available_complete_airfare_across_comparison_origins\n"
    "  comparison_dimensions:\n"
    "  - exact_destination_airport_across_configured_taiwan_origins\n"
    "  - trip_type\n"
    "  - departure_lead_time_bucket\n",
)

replace_once(
    "flight-radar.yaml",
    "  external_anomaly_truth:\n    preferred: true\n",
    "  external_anomaly_truth:\n"
    "    preferred: true\n"
    "    normalization_scope: exact_destination_airport_across_configured_taiwan_origins\n"
    "    google_flight_deals_typical_pool: minimum_qualified_typical_price_for_same_destination_airport_in_current_sweep\n"
    "    candidate_selection: lowest_current_complete_airfare_for_same_destination_airport_before_exact_revalidation\n"
    "    preserve_exact_origin_identity: true\n",
)

replace_once(
    "docs/scoring.md",
    "Formal Deal ordering is deliberately simple and explainable:\n\n1. route-relative anomaly strength, descending;\n2. current complete airfare in TWD, ascending.\n",
    "Formal Deal ordering is deliberately simple and explainable:\n\n"
    "1. destination-airport-relative anomaly strength, descending;\n"
    "2. current complete airfare in TWD, ascending.\n\n"
    "Before exact revalidation, records for the same exact destination airport are normalized across TPE/TSA/RMQ/KHH: Radar keeps the lowest current complete airfare as the concrete candidate, while Google Flight Deals typical-price evidence is conservatively pooled by taking the lowest qualified typical price observed for that same destination airport across the configured Taiwan origins. Exact ticket origin/date identity is preserved. This prevents a sparse or expensive origin-specific route such as TSA→CJU from manufacturing a huge anomaly when another Taiwan origin reaches CJU at a much lower normal fare.\n",
)

replace_once(
    "docs/price-history.md",
    "3. **historical anomaly evidence** — how a current usable fare compares with prior comparable observations for the same route and departure lead-time conditions.\n",
    "3. **historical anomaly evidence** — how a current usable fare compares with prior comparable observations for the same exact destination airport, pooled across accepted Taiwan origins, under matching trip-type and departure lead-time conditions.\n",
)

replace_once(
    "docs/price-history.md",
    "For v0.1, the mandatory comparison key is:\n\n- exact origin airport;\n- exact destination airport;\n- trip type;\n- departure lead-time bucket.\n",
    "For the current policy, the mandatory comparison key is:\n\n"
    "- exact destination airport;\n"
    "- any accepted Taiwan origin among TPE/TSA/RMQ/KHH;\n"
    "- trip type;\n"
    "- departure lead-time bucket.\n\n"
    "The raw observation still retains its exact origin airport for provenance. Origin is deliberately **not** part of the anomaly comparison key: within one Radar run, the historical sample for a destination airport is the lowest usable complete airfare observed across the accepted Taiwan origins.\n",
)

replace_once(
    "docs/price-history.md",
    "A radar run contributes at most **one comparable price sample** for the same exact route + trip type + lead-time bucket. Multiple Web query permutations, editors, OTAs, or duplicate sightings in the same run are provenance, not independent market samples. If a run contains multiple usable complete-trip observations for one comparison key, the run-level historical sample is the lowest observed usable complete-trip price.\n",
    "A radar run contributes at most **one comparable price sample** for the same destination airport + trip type + lead-time bucket. Multiple Taiwan origins, Web query permutations, editors, OTAs, or duplicate sightings in the same run are provenance, not independent market samples. If a run contains multiple usable complete-trip observations for one comparison key, the run-level historical sample is the lowest observed usable complete-trip price across the accepted Taiwan origins.\n",
)

replace_once(
    "docs/production-radar-runtime-2026-08-13.md",
    "7. Qualified Flight Deals and competitive weak seeds enter bounded selective known-route completion. There is no city × date × city brute-force matrix.\n",
    "7. Qualified Flight Deals and competitive weak seeds are first normalized by exact destination airport across TPE/TSA/RMQ/KHH. For each destination airport, the lowest current complete airfare is the preferred concrete candidate for bounded exact completion. There is no city × date × city brute-force matrix.\n",
)

replace_once(
    "docs/production-radar-runtime-2026-08-13.md",
    "11. For Flight Deals, the authority's typical price is compared with the newly revalidated exact current complete airfare. This prevents a stale discovery price from driving formal ranking.\n",
    "11. For Flight Deals, Radar uses the **lowest qualified typical price observed for the same destination airport across the configured Taiwan origins** as the external baseline, then compares that baseline with the newly revalidated exact current complete airfare. An expensive origin-specific typical cannot override a lower same-destination baseline.\n",
)

replace_once(
    "src/cheap_flight_radar/price_history.py",
    '    """Keep one comparable route-floor sample per radar run.\n\n    Multiple source/query sightings in one run are provenance, not independent\n    historical market samples.  The cheapest usable complete-trip observation is\n    retained for that route/trip-type/lead-time comparison run.\n    """\n',
    '    """Keep one comparable destination-floor sample per radar run.\n\n    Multiple Taiwan origins/source/query sightings in one run are provenance,\n    not independent historical market samples.  The cheapest usable complete-trip\n    observation is retained for that destination/trip-type/lead-time run.\n    """\n',
)

replace_once(
    "src/cheap_flight_radar/price_history.py",
    "    current_time = _parse_datetime(current.observed_at)\n    bucket = departure_lead_time_bucket(_days_until_departure(current), policy)\n\n    comparable: list[FareObservation] = []\n",
    "    current_time = _parse_datetime(current.observed_at)\n"
    "    bucket = departure_lead_time_bucket(_days_until_departure(current), policy)\n"
    "    configured_origins_obj = policy.get(\"comparison_origin_airports\", ())\n"
    "    if not isinstance(configured_origins_obj, Sequence) or isinstance(configured_origins_obj, (str, bytes)):\n"
    "        raise TypeError(\"price_history.comparison_origin_airports must be a sequence\")\n"
    "    configured_origins = {str(item) for item in configured_origins_obj}\n"
    "    if configured_origins and current.origin not in configured_origins:\n"
    "        raise ValueError(\"current observation origin is outside configured comparison origins\")\n\n"
    "    comparable: list[FareObservation] = []\n",
)

replace_once(
    "src/cheap_flight_radar/price_history.py",
    "        if (\n            prior.origin != current.origin\n            or prior.destination != current.destination\n            or prior.trip_type != current.trip_type\n        ):\n            continue\n",
    "        if configured_origins and prior.origin not in configured_origins:\n"
    "            continue\n"
    "        if prior.destination != current.destination or prior.trip_type != current.trip_type:\n"
    "            continue\n",
)

replace_once(
    "src/cheap_flight_radar/price_history.py",
    '    """Compare a current fare with prior exact-route, lead-time-matched history."""\n',
    '    """Compare a current fare with prior destination-airport, lead-time-matched history."""\n',
)

replace_once(
    "src/cheap_flight_radar/production_radar.py",
    "    observation_id: str | None = None\n\n    @property\n",
    "    observation_id: str | None = None\n"
    "    anomaly_baseline_twd: int | None = None\n"
    "    anomaly_scope: str | None = None\n\n"
    "    @property\n",
)

replace_once(
    "src/cheap_flight_radar/production_radar.py",
    '        "anomaly_strength_percent": item.anomaly_strength_percent,\n        "current_complete_airfare_twd": item.current_complete_airfare_twd,\n',
    '        "anomaly_strength_percent": item.anomaly_strength_percent,\n'
    '        "anomaly_baseline_twd": item.anomaly_baseline_twd,\n'
    '        "anomaly_scope": item.anomaly_scope,\n'
    '        "current_complete_airfare_twd": item.current_complete_airfare_twd,\n',
)

replace_once(
    "src/cheap_flight_radar/production_radar.py",
    "    return sorted(by_key.values(), key=_discovery_sort_key)\n\n\ndef _select_for_revalidation",
    "    return sorted(by_key.values(), key=_discovery_sort_key)\n\n\n"
    "def _destination_floor_sort_key(record: AirfareRecord) -> tuple[float, float, str]:\n"
    "    return (\n"
    "        float(record.current_price_twd or 10**12),\n"
    "        -float(record.discount_percent or 0.0),\n"
    "        record.record_id,\n"
    "    )\n\n\n"
    "def _dedupe_destination_floor(records: Sequence[AirfareRecord]) -> list[AirfareRecord]:\n"
    "    \"\"\"Keep the cheapest current complete airfare for each exact destination airport.\"\"\"\n\n"
    "    by_destination: dict[str, AirfareRecord] = {}\n"
    "    for record in records:\n"
    "        destination = record.destination.iata\n"
    "        incumbent = by_destination.get(destination)\n"
    "        if incumbent is None or _destination_floor_sort_key(record) < _destination_floor_sort_key(incumbent):\n"
    "            by_destination[destination] = record\n"
    "    return sorted(by_destination.values(), key=_discovery_sort_key)\n\n\n"
    "def _select_for_revalidation",
)

replace_once(
    "src/cheap_flight_radar/production_radar.py",
    "    def _external_truth(self, discovery: AirfareRecord, exact: AirfareRecord) -> AnomalyEvidence | None:\n        evidences: list[AnomalyEvidence] = []\n        if discovery.anomaly_authority == \"google_flight_deals\":\n            evidences.append(\n                AnomalyEvidence(\n                    source=\"google_flight_deals\",\n                    current_price_twd=float(exact.current_price_twd or 0),\n                    typical_price_twd=float(discovery.typical_price_twd) if discovery.typical_price_twd is not None else None,\n                    discount_percent=None,\n                    reproducible=bool(discovery.reproducible_search and exact.reproducible_search),\n                    qualified=(\n                        discovery.evidence_class == \"qualified_round_trip_deal\"\n                        and exact.verification_state == \"revalidated\"\n                        and exact.complete_airfare\n                    ),\n                )\n            )\n",
    "    def _external_truth(\n"
    "        self,\n"
    "        discovery: AirfareRecord,\n"
    "        exact: AirfareRecord,\n"
    "        destination_baseline: AirfareRecord | None,\n"
    "    ) -> AnomalyEvidence | None:\n"
    "        evidences: list[AnomalyEvidence] = []\n"
    "        flight_deals_baseline = destination_baseline\n"
    "        if flight_deals_baseline is None and discovery.anomaly_authority == \"google_flight_deals\":\n"
    "            flight_deals_baseline = discovery\n"
    "        if (\n"
    "            flight_deals_baseline is not None\n"
    "            and flight_deals_baseline.anomaly_authority == \"google_flight_deals\"\n"
    "            and flight_deals_baseline.typical_price_twd is not None\n"
    "        ):\n"
    "            evidences.append(\n"
    "                AnomalyEvidence(\n"
    "                    source=\"google_flight_deals\",\n"
    "                    current_price_twd=float(exact.current_price_twd or 0),\n"
    "                    typical_price_twd=float(flight_deals_baseline.typical_price_twd),\n"
    "                    discount_percent=None,\n"
    "                    reproducible=bool(flight_deals_baseline.reproducible_search and exact.reproducible_search),\n"
    "                    qualified=(\n"
    "                        flight_deals_baseline.evidence_class == \"qualified_round_trip_deal\"\n"
    "                        and exact.verification_state == \"revalidated\"\n"
    "                        and exact.complete_airfare\n"
    "                    ),\n"
    "                )\n"
    "            )\n",
)

replace_once(
    "src/cheap_flight_radar/production_radar.py",
    "        completion_seed_records: list[AirfareRecord] = []\n        weak_signals: list[RadarItem] = []\n",
    "        completion_seed_records: list[AirfareRecord] = []\n"
    "        destination_baselines: dict[str, AirfareRecord] = {}\n"
    "        weak_signals: list[RadarItem] = []\n",
)

replace_once(
    "src/cheap_flight_radar/production_radar.py",
    "                region_records.append(record)\n                market = market_slice(record.destination.country)\n",
    "                region_records.append(record)\n"
    "                if record.anomaly_authority == \"google_flight_deals\" and record.typical_price_twd:\n"
    "                    incumbent_baseline = destination_baselines.get(record.destination.iata)\n"
    "                    if (\n"
    "                        incumbent_baseline is None\n"
    "                        or int(record.typical_price_twd) < int(incumbent_baseline.typical_price_twd or 10**12)\n"
    "                    ):\n"
    "                        destination_baselines[record.destination.iata] = record\n"
    "                market = market_slice(record.destination.country)\n",
)

replace_once(
    "src/cheap_flight_radar/production_radar.py",
    "        candidates = _select_for_revalidation(_dedupe_discovery(completion_seed_records), candidate_limit)\n",
    "        candidates = _select_for_revalidation(\n"
    "            _dedupe_destination_floor(_dedupe_discovery(completion_seed_records)),\n"
    "            candidate_limit,\n"
    "        )\n",
)

replace_once(
    "src/cheap_flight_radar/production_radar.py",
    "            truth = self._external_truth(discovery, exact) or self._history_truth(observation)\n",
    "            destination_baseline = destination_baselines.get(discovery.destination.iata)\n"
    "            truth = self._external_truth(discovery, exact, destination_baseline) or self._history_truth(observation)\n",
)

replace_once(
    "src/cheap_flight_radar/production_radar.py",
    "            deals.append(RadarItem(\"Deal\", \"deal\", discovery, exact, truth.source, discount, \"qualified anomaly authority plus current exact complete airfare\", observation.observation_id))\n",
    "            baseline_twd = int(round(truth.typical_price_twd)) if truth.typical_price_twd is not None else None\n"
    "            anomaly_scope = (\n"
    "                \"destination_airport_all_taiwan_origins\"\n"
    "                if truth.source in {\"google_flight_deals\", \"own_price_history\"}\n"
    "                else \"selected_authority_scope\"\n"
    "            )\n"
    "            deals.append(\n"
    "                RadarItem(\n"
    "                    \"Deal\", \"deal\", discovery, exact, truth.source, discount,\n"
    "                    \"qualified anomaly authority plus current exact complete airfare\",\n"
    "                    observation.observation_id, anomaly_baseline_twd=baseline_twd, anomaly_scope=anomaly_scope,\n"
    "                )\n"
    "            )\n",
)

replace_once(
    "src/cheap_flight_radar/production_radar.py",
    '            "destination_scope": "asia_oceania",\n            "fixed_watch_is_deal_coverage_authority": False,\n',
    '            "destination_scope": "asia_oceania",\n'
    '            "anomaly_normalization": "exact_destination_airport_across_tpe_tsa_rmq_khh",\n'
    '            "same_destination_candidate_rule": "lowest_current_complete_airfare",\n'
    '            "same_destination_typical_rule": "lowest_qualified_google_flight_deals_typical",\n'
    '            "fixed_watch_is_deal_coverage_authority": False,\n',
)

replace_once(
    "src/cheap_flight_radar/production_publication.py",
    '    return f"{number:.1f}% below typical"\n',
    '    return f"{number:.1f}% below baseline"\n',
)

replace_once(
    "src/cheap_flight_radar/production_publication.py",
    "    typical = discovery.get(\"typical_price_twd\")\n    anomaly = item.get(\"anomaly_strength_percent\")\n",
    "    anomaly_scope = str(item.get(\"anomaly_scope\") or \"\")\n"
    "    if item.get(\"anomaly_baseline_twd\") is not None:\n"
    "        typical = item.get(\"anomaly_baseline_twd\")\n"
    "        baseline_label = \"Destination baseline\" if anomaly_scope == \"destination_airport_all_taiwan_origins\" else \"Selected baseline\"\n"
    "    else:\n"
    "        typical = discovery.get(\"typical_price_twd\")\n"
    "        baseline_label = \"Provider typical (legacy)\"\n"
    "    anomaly = item.get(\"anomaly_strength_percent\")\n",
)

replace_once(
    "src/cheap_flight_radar/production_publication.py",
    '        f\'<span class="metric"><small>Typical</small><strong>{escape(_money(typical))}</strong></span>\'\n',
    '        f\'<span class="metric"><small>{escape(baseline_label)}</small><strong>{escape(_money(typical))}</strong></span>\'\n',
)

replace_once(
    "src/cheap_flight_radar/production_publication.py",
    "        '<h1>Qualified cheap airfare Deals</h1>'\n        '<p class=\"hero-copy\">Deals are ranked by route-relative anomaly strength, then current complete airfare. Signals remain separate and cannot outrank a Deal.</p>'\n",
    "        '<h1>Qualified cheap airfare Deals</h1>'\n"
    "        '<p class=\"hero-copy\">Deals are ranked by destination-airport anomaly strength across accepted Taiwan origins, then current complete airfare. Signals remain separate and cannot outrank a Deal.</p>'\n",
)

replace_once(
    "src/cheap_flight_radar/production_publication.py",
    "        '<li><span>Flight Deals</span><span class=\"status-badge good\">Deal truth</span></li>'\n",
    "        '<li><span>Flight Deals</span><span class=\"status-badge good\">destination-airport truth</span></li>'\n",
)

replace_once(
    "src/cheap_flight_radar/production_publication.py",
    "        + '<p class=\"provenance\">Own price history is supplemental/fallback anomaly evidence; sparse history cannot block a Deal already qualified by a higher-priority external authority.<br>'\n",
    "        + '<p class=\"provenance\">Destination-airport anomaly baselines pool TPE/TSA/RMQ/KHH while each ticket retains its actual origin. Own price history is supplemental/fallback evidence; sparse history cannot block a Deal already qualified by a higher-priority external authority.<br>'\n",
)

replace_once(
    "tests/test_price_history.py",
    "        self.assertEqual(self.policy[\"percentile\"][\"minimum_samples\"], 10)\n",
    "        self.assertEqual(self.policy[\"percentile\"][\"minimum_samples\"], 10)\n"
    "        self.assertEqual(self.policy[\"comparison_origin_airports\"], [\"TPE\", \"TSA\", \"RMQ\", \"KHH\"])\n",
)

replace_once(
    "tests/test_price_history.py",
    "    def test_comparison_uses_same_route_trip_type_and_lead_bucket(self):\n        current = obs(\"current\", departure_date=\"2026-08-21\", price=4000)\n        history = [\n            obs(\"same-1\", radar_run_id=\"r1\", observed_at=\"2026-08-01T12:00:00+00:00\", departure_date=\"2026-08-11\", price=5000),\n            obs(\"same-2\", radar_run_id=\"r2\", observed_at=\"2026-08-02T12:00:00+00:00\", departure_date=\"2026-08-12\", price=5200),\n            obs(\"same-3\", radar_run_id=\"r3\", observed_at=\"2026-08-03T12:00:00+00:00\", departure_date=\"2026-08-13\", price=5400),\n            obs(\"wrong-route\", radar_run_id=\"r4\", observed_at=\"2026-08-04T12:00:00+00:00\", destination=\"PUS\", departure_date=\"2026-08-14\", price=1000),\n            obs(\"wrong-bucket\", radar_run_id=\"r5\", observed_at=\"2026-08-01T12:00:00+00:00\", departure_date=\"2026-09-20\", price=1000),\n        ]\n",
    "    def test_comparison_pools_allowed_origins_for_same_destination_trip_type_and_lead_bucket(self):\n"
    "        current = obs(\"current\", departure_date=\"2026-08-21\", price=4000)\n"
    "        history = [\n"
    "            obs(\"same-1\", radar_run_id=\"r1\", origin=\"KHH\", observed_at=\"2026-08-01T12:00:00+00:00\", departure_date=\"2026-08-11\", price=5000),\n"
    "            obs(\"same-2\", radar_run_id=\"r2\", origin=\"RMQ\", observed_at=\"2026-08-02T12:00:00+00:00\", departure_date=\"2026-08-12\", price=5200),\n"
    "            obs(\"same-3\", radar_run_id=\"r3\", origin=\"TSA\", observed_at=\"2026-08-03T12:00:00+00:00\", departure_date=\"2026-08-13\", price=5400),\n"
    "            obs(\"wrong-destination\", radar_run_id=\"r4\", observed_at=\"2026-08-04T12:00:00+00:00\", destination=\"PUS\", departure_date=\"2026-08-14\", price=1000),\n"
    "            obs(\"wrong-origin\", radar_run_id=\"r6\", origin=\"KNH\", observed_at=\"2026-08-04T12:00:00+00:00\", departure_date=\"2026-08-14\", price=900),\n"
    "            obs(\"wrong-bucket\", radar_run_id=\"r5\", observed_at=\"2026-08-01T12:00:00+00:00\", departure_date=\"2026-09-20\", price=1000),\n"
    "        ]\n",
)

replace_once(
    "tests/test_production_radar.py",
    "    async def test_exact_failure_is_signal_and_never_guessed_into_deal(self):\n",
    "    async def test_same_destination_uses_cheapest_origin_and_lowest_typical_baseline(self):\n"
    "        adapter = FakeAdapter({\n"
    "            \"TPE\": [],\n"
    "            \"TSA\": [deal(\"TSA\", \"CJU\", \"South Korea\", 17639, 63237, 72)],\n"
    "            \"RMQ\": [deal(\"RMQ\", \"CJU\", \"South Korea\", 9023, 11576, 22)],\n"
    "            \"KHH\": [],\n"
    "        })\n"
    "        result = await ProductionRadar(policy=self.policy, adapter=adapter).run(run_at=RUN_AT)\n"
    "        cju = next(item for item in result.deals if item.discovery.destination.iata == \"CJU\")\n"
    "        self.assertEqual(cju.discovery.origin.iata, \"RMQ\")\n"
    "        self.assertEqual(cju.current_complete_airfare_twd, 9023)\n"
    "        self.assertEqual(cju.anomaly_baseline_twd, 11576)\n"
    "        self.assertEqual(cju.anomaly_scope, \"destination_airport_all_taiwan_origins\")\n"
    "        self.assertAlmostEqual(cju.anomaly_strength_percent or 0, (11576 - 9023) / 11576 * 100)\n"
    "        self.assertIn((\"RMQ\", \"CJU\", \"2026-09-10\", \"2026-09-14\"), adapter.exact_calls)\n"
    "        self.assertNotIn((\"TSA\", \"CJU\", \"2026-09-10\", \"2026-09-14\"), adapter.exact_calls)\n\n"
    "    async def test_exact_failure_is_signal_and_never_guessed_into_deal(self):\n",
)

replace_once(
    "tests/test_production_publication.py",
    '            "observation_id": observation.observation_id, "anomaly_source": "google_flight_deals", "anomaly_strength_percent": 31.0,\n            "current_complete_airfare_twd": 6900, "discovery": asdict(discovery), "exact": asdict(exact),\n',
    '            "observation_id": observation.observation_id, "anomaly_source": "google_flight_deals", "anomaly_strength_percent": 31.0,\n'
    '            "anomaly_baseline_twd": 10000, "anomaly_scope": "destination_airport_all_taiwan_origins",\n'
    '            "current_complete_airfare_twd": 6900, "discovery": asdict(discovery), "exact": asdict(exact),\n',
)

replace_once(
    "tests/test_production_publication.py",
    '            self.assertIn("31.0% below typical", text)\n',
    '            self.assertIn("31.0% below baseline", text)\n'
    '            self.assertIn("Destination baseline", text)\n',
)

# The one-shot workflow restores ci.yml and removes this patcher before committing.
print("destination-airport normalization patch applied")
