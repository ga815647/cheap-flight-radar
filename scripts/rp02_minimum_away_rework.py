from pathlib import Path


def replace_if_missing(path: str, *, marker: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    if marker in text:
        return
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one anchor for {marker!r}, found {count}")
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_if_missing(
    "flight-radar.yaml",
    marker="minimum_away_hours_reference: return_windows_policy.formal_deal_minimum_away_hours",
    old="""      require_exact_outbound_and_return_dates: true\n      require_concrete_itinerary_identity: true\n""",
    new="""      require_exact_outbound_and_return_dates: true\n      require_minimum_destination_stay: true\n      minimum_away_hours_reference: return_windows_policy.formal_deal_minimum_away_hours\n      minimum_away_comparison: strict_greater_than\n      require_concrete_itinerary_identity: true\n""",
)
replace_if_missing(
    "flight-radar.yaml",
    marker="future_observed_at_action: exclude_fail_closed",
    old="""      require_current_observation: true\n      max_observation_age_hours: 24\n""",
    new="""      require_current_observation: true\n      max_observation_age_hours: 24\n      future_observed_at_action: exclude_fail_closed\n""",
)
replace_if_missing(
    "flight-radar.yaml",
    marker="destination_stay_at_or_below_minimum_away_hours",
    old="""    - stale_only_evidence\n    - formal_deal\n""",
    new="""    - stale_only_evidence\n    - destination_stay_at_or_below_minimum_away_hours\n    - formal_deal\n""",
)

replace_if_missing(
    "src/cheap_flight_radar/ftr_absolute_low.py",
    marker="FORMAL_DEAL_MINIMUM_AWAY_HOURS, RadarItem, RadarRunResult, _minimum_away_satisfied",
    old="from .production_radar import RadarItem, RadarRunResult\n",
    new="from .production_radar import FORMAL_DEAL_MINIMUM_AWAY_HOURS, RadarItem, RadarRunResult, _minimum_away_satisfied\n",
)
replace_if_missing(
    "src/cheap_flight_radar/ftr_absolute_low.py",
    marker="absolute-low minimum-away reference drifted",
    old="""    if tuple(str(value) for value in (eligibility.get(\"allowed_surfaces\") or ())) != (\"exact\", \"open_jaw\"):\n        raise FTRAbsoluteLowPolicyError(\"absolute-low allowed_surfaces drifted\")\n    required_eligibility_flags = (\n""",
    new="""    if tuple(str(value) for value in (eligibility.get(\"allowed_surfaces\") or ())) != (\"exact\", \"open_jaw\"):\n        raise FTRAbsoluteLowPolicyError(\"absolute-low allowed_surfaces drifted\")\n    if str(eligibility.get(\"minimum_away_hours_reference\") or \"\") != \"return_windows_policy.formal_deal_minimum_away_hours\":\n        raise FTRAbsoluteLowPolicyError(\"absolute-low minimum-away reference drifted\")\n    if str(eligibility.get(\"minimum_away_comparison\") or \"\") != \"strict_greater_than\":\n        raise FTRAbsoluteLowPolicyError(\"absolute-low minimum-away comparison drifted\")\n    return_windows_policy = _mapping(policy.get(\"return_windows_policy\"))\n    minimum_away_hours = return_windows_policy.get(\"formal_deal_minimum_away_hours\")\n    if (\n        isinstance(minimum_away_hours, bool)\n        or not isinstance(minimum_away_hours, (int, float))\n        or float(minimum_away_hours) != float(FORMAL_DEAL_MINIMUM_AWAY_HOURS)\n    ):\n        raise FTRAbsoluteLowPolicyError(\"absolute-low minimum-away SSOT drifted from CFR runtime semantics\")\n    if str(eligibility.get(\"future_observed_at_action\") or \"\") != \"exclude_fail_closed\":\n        raise FTRAbsoluteLowPolicyError(\"absolute-low future observed_at action drifted\")\n    required_eligibility_flags = (\n""",
)
replace_if_missing(
    "src/cheap_flight_radar/ftr_absolute_low.py",
    marker='"require_minimum_destination_stay",',
    old="""        \"require_exact_outbound_and_return_dates\",\n        \"require_concrete_itinerary_identity\",\n""",
    new="""        \"require_exact_outbound_and_return_dates\",\n        \"require_minimum_destination_stay\",\n        \"require_concrete_itinerary_identity\",\n""",
)
replace_if_missing(
    "src/cheap_flight_radar/ftr_absolute_low.py",
    marker="if not _minimum_away_satisfied(exact, int(minimum_away_hours)):",
    old="""    if _exact_dates(exact) is None or not exact.record_id or not exact.legs:\n        return False\n    if exact.origin.iata not in {str(value) for value in policy_root_search(policy).get(\"origin_airports\", ())}:\n""",
    new="""    if _exact_dates(exact) is None or not exact.record_id or not exact.legs:\n        return False\n    root_policy = _mapping(policy.get(\"_root_policy\"))\n    minimum_away_hours = _mapping(root_policy.get(\"return_windows_policy\")).get(\"formal_deal_minimum_away_hours\")\n    if isinstance(minimum_away_hours, bool) or not isinstance(minimum_away_hours, (int, float)):\n        return False\n    if not _minimum_away_satisfied(exact, int(minimum_away_hours)):\n        return False\n    if exact.origin.iata not in {str(value) for value in policy_root_search(policy).get(\"origin_airports\", ())}:\n""",
)
replace_if_missing(
    "src/cheap_flight_radar/ftr_absolute_low.py",
    marker="if delta_seconds < 0:",
    old="""    max_age = int(eligibility[\"max_observation_age_hours\"])\n    delta_hours = abs((run_at - observed_at).total_seconds()) / 3600.0\n    if delta_hours > max_age:\n        return False\n""",
    new="""    max_age = int(eligibility[\"max_observation_age_hours\"])\n    delta_seconds = (run_at - observed_at).total_seconds()\n    if delta_seconds < 0:\n        return False\n    delta_hours = delta_seconds / 3600.0\n    if delta_hours > max_age:\n        return False\n""",
)

replace_if_missing(
    "docs/ftr-handoff.md",
    marker="same strict >24-hour minimum-away rule",
    old="The machine policy lives at `ftr_handoff.absolute_low_non_deal_producer` in `flight-radar.yaml`. Eligibility requires a non-Deal `exact_revalidated_candidate` with a positive complete outbound+return fare, exact dates, concrete/reproducible itinerary identity, current timezone-aware observation, and existing CFR revalidation/provenance evidence. Weak seeds, cached/promotional hints, incomplete/non-converged/non-exact/stale evidence and anything matching a formal Deal identity fail closed.\n",
    new="The machine policy lives at `ftr_handoff.absolute_low_non_deal_producer` in `flight-radar.yaml`. Eligibility requires a non-Deal `exact_revalidated_candidate` with a positive complete outbound+return fare, exact dates, the same strict >24-hour minimum-away rule already used by CFR production, concrete/reproducible itinerary identity, a current timezone-aware observation that is not later than the run timestamp, and existing CFR revalidation/provenance evidence. The minimum-away threshold is deterministically tied to `return_windows_policy.formal_deal_minimum_away_hours`; weak seeds, cached/promotional hints, incomplete/non-converged/non-exact/stale or future-dated evidence, <=24-hour destination stays, and anything matching a formal Deal identity fail closed.\n",
)

replace_if_missing(
    "tests/test_ftr_absolute_low.py",
    marker='observed_at: str = "2026-08-19T07:55:00+08:00"',
    old='    observed_at: str = "2026-08-19T08:05:00+08:00",\n',
    new='    observed_at: str = "2026-08-19T07:55:00+08:00",\n',
)
replace_if_missing(
    "tests/test_ftr_absolute_low.py",
    marker="def timed_exact_record(",
    old="""\ndef radar_item(\n""",
    new="""\ndef timed_exact_record(\n    record_id: str,\n    *,\n    return_departure_time: str,\n    observed_at: str = \"2026-08-19T07:55:00+08:00\",\n) -> AirfareRecord:\n    base = exact_record(\n        record_id,\n        outbound_date=\"2026-10-05\",\n        return_date=\"2026-10-06\",\n        observed_at=observed_at,\n    )\n    return replace(\n        base,\n        legs=(\n            AirfareLeg(\n                \"TPE\",\n                \"KIX\",\n                \"2026-10-05\",\n                \"2026-10-05T08:00:00+08:00\",\n                \"2026-10-05T12:00:00+09:00\",\n            ),\n            AirfareLeg(\n                \"KIX\",\n                \"TPE\",\n                \"2026-10-06\",\n                return_departure_time,\n                \"2026-10-06T16:00:00+08:00\",\n            ),\n        ),\n    )\n\n\ndef radar_item(\n""",
)
replace_if_missing(
    "tests/test_ftr_absolute_low.py",
    marker="def test_minimum_away_reuses_cfr_strict_greater_than_semantics",
    old="""    def test_existing_open_jaw_identity_is_preserved_without_new_search_behavior(self):\n""",
    new="""    def test_minimum_away_reuses_cfr_strict_greater_than_semantics(self):\n        at_boundary = radar_item(\n            timed_exact_record(\n                \"stay-24h\",\n                return_departure_time=\"2026-10-06T12:00:00+09:00\",\n            )\n        )\n        over_boundary = radar_item(\n            timed_exact_record(\n                \"stay-25h\",\n                return_departure_time=\"2026-10-06T13:00:00+09:00\",\n            )\n        )\n        selected = select_absolute_low_non_deals(\n            run_result(pool=(at_boundary, over_boundary)),\n            policy=deepcopy(self.policy),\n        )\n        self.assertEqual([item.exact.record_id for item in selected], [\"stay-25h\"])\n\n    def test_future_observed_at_fails_closed(self):\n        future = radar_item(\n            exact_record(\n                \"future-observation\",\n                observed_at=\"2026-08-19T08:00:01+08:00\",\n            )\n        )\n        self.assertEqual(\n            select_absolute_low_non_deals(run_result(pool=(future,)), policy=deepcopy(self.policy)),\n            (),\n        )\n\n    def test_existing_open_jaw_identity_is_preserved_without_new_search_behavior(self):\n""",
)
replace_if_missing(
    "tests/test_ftr_absolute_low.py",
    marker="minimum-away reference drifted",
    old="""        for field, value, message in drift_cases:\n            with self.subTest(field=field):\n                drifted = deepcopy(self.policy)\n                drifted[\"ftr_handoff\"][\"absolute_low_non_deal_producer\"][field] = value\n                with self.assertRaisesRegex(FTRAbsoluteLowPolicyError, message):\n                    validate_absolute_low_policy(drifted)\n\n\nclass NonAnomalyRuntimeAdapter:\n""",
    new="""        for field, value, message in drift_cases:\n            with self.subTest(field=field):\n                drifted = deepcopy(self.policy)\n                drifted[\"ftr_handoff\"][\"absolute_low_non_deal_producer\"][field] = value\n                with self.assertRaisesRegex(FTRAbsoluteLowPolicyError, message):\n                    validate_absolute_low_policy(drifted)\n\n        drifted_reference = deepcopy(self.policy)\n        drifted_reference[\"ftr_handoff\"][\"absolute_low_non_deal_producer\"][\"eligibility\"][\"minimum_away_hours_reference\"] = \"other.policy\"\n        with self.assertRaisesRegex(FTRAbsoluteLowPolicyError, \"minimum-away reference drifted\"):\n            validate_absolute_low_policy(drifted_reference)\n\n        drifted_threshold = deepcopy(self.policy)\n        drifted_threshold[\"return_windows_policy\"][\"formal_deal_minimum_away_hours\"] = 25\n        with self.assertRaisesRegex(FTRAbsoluteLowPolicyError, \"minimum-away SSOT drifted\"):\n            validate_absolute_low_policy(drifted_threshold)\n\n\nclass NonAnomalyRuntimeAdapter:\n""",
)
replace_if_missing(
    "tests/test_ftr_absolute_low.py",
    marker='observed_at="2026-08-19T07:55:00+08:00",',
    old='            observed_at="2026-08-19T08:05:00+08:00",\n',
    new='            observed_at="2026-08-19T07:55:00+08:00",\n',
)
replace_if_missing(
    "tests/test_ftr_absolute_low.py",
    marker="class ShortStayRuntimeAdapter",
    old="""\n\nclass AbsoluteLowRuntimeIntegrationTest(unittest.IsolatedAsyncioTestCase):\n""",
    new="""\n\nclass ShortStayRuntimeAdapter(NonAnomalyRuntimeAdapter):\n    def __init__(self):\n        super().__init__()\n        self.seed = replace(\n            self.seed,\n            legs=(\n                AirfareLeg(\"TPE\", \"KIX\", \"2026-10-05\"),\n                AirfareLeg(\"KIX\", \"TPE\", \"2026-10-06\"),\n            ),\n        )\n\n    async def exact(self, *, origin, destination, departure_date, return_date=None, **kwargs):\n        record = timed_exact_record(\n            \"runtime-short-stay\",\n            return_departure_time=\"2026-10-06T11:00:00+09:00\",\n        )\n        return ProviderResult(\"gflights\", \"exact\", \"complete\", (record,))\n\n\nclass AbsoluteLowRuntimeIntegrationTest(unittest.IsolatedAsyncioTestCase):\n""",
)
replace_if_missing(
    "tests/test_ftr_absolute_low.py",
    marker="test_production_minimum_away_downgrade_is_not_repromoted",
    old="""        self.assertFalse(any(item.state == OUTPUT_STATE for item in result.signals))\n\n\nif __name__ == \"__main__\":\n""",
    new="""        self.assertFalse(any(item.state == OUTPUT_STATE for item in result.signals))\n\n    async def test_production_minimum_away_downgrade_is_not_repromoted(self):\n        policy = yaml.safe_load((ROOT / \"flight-radar.yaml\").read_text(encoding=\"utf-8\"))\n        result = await run_once(policy=policy, adapter=ShortStayRuntimeAdapter(), run_at=RUN_AT)\n        self.assertTrue(\n            any(\n                item.exact is not None and item.exact.record_id == \"runtime-short-stay\"\n                for item in result.exact_non_deal_candidates\n            )\n        )\n        self.assertFalse(\n            any(\n                item.exact is not None and item.exact.record_id == \"runtime-short-stay\"\n                for item in result.ftr_absolute_low_non_deals\n            )\n        )\n\n\nif __name__ == \"__main__\":\n""",
)

print("RP-02 minimum-away rework applied")
