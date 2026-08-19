from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise SystemExit(f"{path}: expected one review-fix anchor, found {text.count(old)}")
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "src/cheap_flight_radar/production_radar.py",
    '''        return RadarRunResult(\n  run_id,\n  local_run_at.isoformat(),\n  tuple(deals),\n  tuple(signal_by_key.values()),\n  coverage,\n  tuple(provider_failures),\n  exact_non_deal_candidates=tuple(\n      item\n      for item in exact_signals\n      if item.state == "exact_revalidated_candidate" and item.exact is not None\n  ),\n        )\n''',
    '''        return RadarRunResult(\n            run_id,\n            local_run_at.isoformat(),\n            tuple(deals),\n            tuple(signal_by_key.values()),\n            coverage,\n            tuple(provider_failures),\n            exact_non_deal_candidates=tuple(\n                item\n                for item in exact_signals\n                if item.state == "exact_revalidated_candidate" and item.exact is not None\n            ),\n        )\n''',
)

replace_once(
    "src/cheap_flight_radar/ftr_absolute_low.py",
    '''    if str(producer.get("output_state") or "") != OUTPUT_STATE:\n        raise FTRAbsoluteLowPolicyError("absolute-low producer output_state drifted")\n    if tuple(str(value) for value in (producer.get("input_states") or ())) != SUPPORTED_INPUT_STATES:\n''',
    '''    if str(producer.get("output_state") or "") != OUTPUT_STATE:\n        raise FTRAbsoluteLowPolicyError("absolute-low producer output_state drifted")\n    if str(producer.get("contract_state") or "") != "implemented_pre_activation":\n        raise FTRAbsoluteLowPolicyError("absolute-low producer contract_state drifted")\n    if str(producer.get("source_collection") or "") != "current_run_exact_non_deal_candidates":\n        raise FTRAbsoluteLowPolicyError("absolute-low producer source_collection drifted")\n    if tuple(str(value) for value in (producer.get("input_states") or ())) != SUPPORTED_INPUT_STATES:\n''',
)
replace_once(
    "src/cheap_flight_radar/ftr_absolute_low.py",
    '''    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:\n        raise FTRAbsoluteLowPolicyError("absolute-low max_selected_count must be a positive integer")\n    eligibility = _mapping(producer.get("eligibility"))\n''',
    '''    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:\n        raise FTRAbsoluteLowPolicyError("absolute-low max_selected_count must be a positive integer")\n    if budget.get("independent_of_search_final_shortlist_limit") is not True:\n        raise FTRAbsoluteLowPolicyError("absolute-low budget must remain independent of search shortlist")\n    if budget.get("independent_of_publication_display_limits") is not True:\n        raise FTRAbsoluteLowPolicyError("absolute-low budget must remain independent of publication limits")\n    if budget.get("new_provider_calls") != 0:\n        raise FTRAbsoluteLowPolicyError("absolute-low producer must not add provider calls")\n    eligibility = _mapping(producer.get("eligibility"))\n''',
)
replace_once(
    "src/cheap_flight_radar/ftr_absolute_low.py",
    '''    if tuple(str(value) for value in (eligibility.get("allowed_surfaces") or ())) != ("exact", "open_jaw"):\n        raise FTRAbsoluteLowPolicyError("absolute-low allowed_surfaces drifted")\n    isolation = _mapping(producer.get("generic_signal_isolation"))\n''',
    '''    if tuple(str(value) for value in (eligibility.get("allowed_surfaces") or ())) != ("exact", "open_jaw"):\n        raise FTRAbsoluteLowPolicyError("absolute-low allowed_surfaces drifted")\n    required_eligibility_flags = (\n        "require_non_deal",\n        "require_exact_record",\n        "require_complete_outbound_return_airfare",\n        "require_positive_complete_airfare_twd",\n        "require_exact_outbound_and_return_dates",\n        "require_concrete_itinerary_identity",\n        "require_reproducible_search_identity",\n        "require_source_evidence_provenance",\n        "require_existing_cfr_revalidation_trust",\n        "require_current_observation",\n    )\n    if any(eligibility.get(field) is not True for field in required_eligibility_flags):\n        raise FTRAbsoluteLowPolicyError("absolute-low required eligibility flags drifted")\n    if tuple(str(value) for value in (eligibility.get("trusted_evidence_any_of") or ())) != (\n        "booking_url",\n        "evidence_url",\n        "booking_token",\n        "provider_leg_identity",\n    ):\n        raise FTRAbsoluteLowPolicyError("absolute-low trusted evidence contract drifted")\n    isolation = _mapping(producer.get("generic_signal_isolation"))\n''',
)
replace_once(
    "src/cheap_flight_radar/ftr_absolute_low.py",
    '''    if isolation.get("classification_signal_alone_is_ineligible") is not True:\n        raise FTRAbsoluteLowPolicyError("Signal classification alone must remain ineligible")\n    deal_isolation = _mapping(producer.get("deal_isolation"))\n    if deal_isolation.get("formal_deal_relabel_or_duplicate") != "forbidden":\n        raise FTRAbsoluteLowPolicyError("formal Deal relabel/duplicate must remain forbidden")\n    canonical = _mapping(ftr.get("canonical_activation"))\n''',
    '''    if isolation.get("classification_signal_alone_is_ineligible") is not True:\n        raise FTRAbsoluteLowPolicyError("Signal classification alone must remain ineligible")\n    if isolation.get("weak_seed_promotion") != "forbidden":\n        raise FTRAbsoluteLowPolicyError("weak-seed promotion must remain forbidden")\n    if isolation.get("cached_or_promotional_hint_promotion") != "forbidden":\n        raise FTRAbsoluteLowPolicyError("cached/promotional hint promotion must remain forbidden")\n    deal_isolation = _mapping(producer.get("deal_isolation"))\n    if deal_isolation.get("formal_deal_input") != "excluded":\n        raise FTRAbsoluteLowPolicyError("formal Deal input must remain excluded")\n    if deal_isolation.get("matching_deal_record_or_itinerary") != "excluded":\n        raise FTRAbsoluteLowPolicyError("matching Deal identity must remain excluded")\n    if deal_isolation.get("formal_deal_relabel_or_duplicate") != "forbidden":\n        raise FTRAbsoluteLowPolicyError("formal Deal relabel/duplicate must remain forbidden")\n    if str(producer.get("anomaly_ranking_role") or "") != "none":\n        raise FTRAbsoluteLowPolicyError("absolute-low producer must not become anomaly ranking")\n    if str(producer.get("ftr_weighted_score") or "") != "forbidden":\n        raise FTRAbsoluteLowPolicyError("FTR weighted score must remain forbidden")\n    if producer.get("normal_cfr_deal_ranking_unchanged") is not True:\n        raise FTRAbsoluteLowPolicyError("normal CFR Deal ranking must remain unchanged")\n    if producer.get("preserve_existing_route_identity") is not True:\n        raise FTRAbsoluteLowPolicyError("existing route identity preservation drifted")\n    if str(producer.get("rp06_new_open_jaw_or_return_gateway_acquisition") or "") != "out_of_scope":\n        raise FTRAbsoluteLowPolicyError("RP-06 acquisition boundary drifted")\n    if str(producer.get("canonical_ftr_activation") or "") != "pending_disabled_until_RP-04":\n        raise FTRAbsoluteLowPolicyError("canonical FTR activation boundary drifted")\n    canonical = _mapping(ftr.get("canonical_activation"))\n''',
)

replace_once(
    "tests/test_ftr_absolute_low.py",
    '''        invalid = (\n            radar_item(replace(base, record_id="incomplete", complete_airfare=False)),\n            radar_item(replace(base, record_id="nonexact", verification_state="exact_search")),\n            radar_item(replace(base, record_id="wrong-class", evidence_class="weak_seed")),\n            radar_item(replace(base, record_id="stale", observed_at="2026-08-17T00:00:00+08:00")),\n            radar_item(replace(base, record_id="no-provenance", booking_token=None, legs=(AirfareLeg("TPE", "KIX", "2026-10-05"),))),\n            radar_item(None, state="weak_seed"),\n        )\n''',
    '''        invalid = (\n            radar_item(replace(base, record_id="incomplete", complete_airfare=False)),\n            radar_item(replace(base, record_id="nonexact", verification_state="exact_search")),\n            radar_item(replace(base, record_id="wrong-class", evidence_class="weak_seed")),\n            radar_item(replace(base, record_id="failed"), state="exact_search_failed"),\n            radar_item(replace(base, record_id="non-converged"), state="exact_search_non_converged"),\n            radar_item(replace(base, record_id="stale", observed_at="2026-08-17T00:00:00+08:00")),\n            radar_item(replace(base, record_id="no-provenance", booking_token=None, legs=(AirfareLeg("TPE", "KIX", "2026-10-05"),))),\n            radar_item(None, state="weak_seed"),\n        )\n''',
)
replace_once(
    "tests/test_ftr_absolute_low.py",
    '''    def test_equal_price_ties_have_stable_complete_order(self):\n        pool = (\n            radar_item(exact_record("z-id", price=3000)),\n            radar_item(exact_record("a-id", price=3000)),\n        )\n        selected = select_absolute_low_non_deals(run_result(pool=pool), policy=deepcopy(self.policy))\n        self.assertEqual([item.exact.record_id for item in selected], ["a-id"])\n''',
    '''    def test_equal_price_ties_have_stable_complete_order(self):\n        first = exact_record("a-id", price=3000)\n        second = replace(\n            exact_record("z-id", price=3000),\n            legs=(AirfareLeg("TPE", "KIX", "2026-10-05", "09:00+08:00", "13:00+09:00"),),\n        )\n        pool = (radar_item(second), radar_item(first))\n        selected = select_absolute_low_non_deals(run_result(pool=pool), policy=deepcopy(self.policy))\n        self.assertEqual([item.exact.record_id for item in selected], ["a-id", "z-id"])\n''',
)
replace_once(
    "tests/test_ftr_absolute_low.py",
    '''        drifted = deepcopy(self.policy)\n        drifted["ftr_handoff"]["absolute_low_non_deal_producer"]["ordering"] = ["record_id_asc"]\n        with self.assertRaisesRegex(FTRAbsoluteLowPolicyError, "ordering drifted"):\n            validate_absolute_low_policy(drifted)\n''',
    '''        drift_cases = (\n            ("source_collection", "generic_signals", "source_collection drifted"),\n            ("ordering", ["record_id_asc"], "ordering drifted"),\n        )\n        for field, value, message in drift_cases:\n            with self.subTest(field=field):\n                drifted = deepcopy(self.policy)\n                drifted["ftr_handoff"]["absolute_low_non_deal_producer"][field] = value\n                with self.assertRaisesRegex(FTRAbsoluteLowPolicyError, message):\n                    validate_absolute_low_policy(drifted)\n''',
)

print("RP-02 final review fixes applied")
