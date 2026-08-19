from __future__ import annotations

from pathlib import Path


def replace_if_missing(path: str, *, marker: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    if marker in text:
        return
    if old not in text:
        raise SystemExit(f"{path}: missing continuation anchor for {marker}")
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


def run_embedded_payload() -> None:
    text = Path(".github/workflows/rp02-bootstrap.yml").read_text(encoding="utf-8")
    start = text.index("          python - <<'PY'\n") + len("          python - <<'PY'\n")
    end = text.index("\n          PY\n", start)
    body = text[start:end]
    body = "\n".join(line[10:] if line.startswith("          ") else line for line in body.splitlines()) + "\n"
    try:
        exec(compile(body, "/tmp/rp02_apply.py", "exec"), {"__name__": "__main__"})
    except SystemExit as exc:
        print(f"embedded payload stopped at expected non-idempotent anchor: {exc}")


run_embedded_payload()

replace_if_missing(
    "src/cheap_flight_radar/production_radar.py",
    marker="exact_non_deal_candidates: tuple[RadarItem, ...] = ()",
    old="""class RadarRunResult:\n    radar_run_id: str\n    run_at: str\n    deals: tuple[RadarItem, ...]\n    signals: tuple[RadarItem, ...]\n    coverage: Mapping[str, Any]\n    provider_failures: tuple[Mapping[str, str], ...]\n""",
    new="""class RadarRunResult:\n    radar_run_id: str\n    run_at: str\n    deals: tuple[RadarItem, ...]\n    signals: tuple[RadarItem, ...]\n    coverage: Mapping[str, Any]\n    provider_failures: tuple[Mapping[str, str], ...]\n    exact_non_deal_candidates: tuple[RadarItem, ...] = ()\n    ftr_absolute_low_non_deals: tuple[RadarItem, ...] = ()\n""",
)
replace_if_missing(
    "src/cheap_flight_radar/production_radar.py",
    marker="exact_non_deal_candidates=tuple(",
    old="        return RadarRunResult(run_id, local_run_at.isoformat(), tuple(deals), tuple(signal_by_key.values()), coverage, tuple(provider_failures))\n",
    new="""        return RadarRunResult(\n            run_id,\n            local_run_at.isoformat(),\n            tuple(deals),\n            tuple(signal_by_key.values()),\n            coverage,\n            tuple(provider_failures),\n            exact_non_deal_candidates=tuple(\n                item\n                for item in exact_signals\n                if item.state == \"exact_revalidated_candidate\" and item.exact is not None\n            ),\n        )\n""",
)
replace_if_missing(
    "src/cheap_flight_radar/production_radar.py",
    marker='"ftr_absolute_low_non_deal_count": len(result.ftr_absolute_low_non_deals)',
    old="""                \"deal_count\": len(result.deals),\n                \"signal_count\": len(result.signals),\n                \"deals\": [_item_json(item) for item in result.deals],\n                \"coverage\": result.coverage,\n""",
    new="""                \"deal_count\": len(result.deals),\n                \"signal_count\": len(result.signals),\n                \"ftr_absolute_low_non_deal_count\": len(result.ftr_absolute_low_non_deals),\n                \"deals\": [_item_json(item) for item in result.deals],\n                \"ftr_absolute_low_non_deals\": [_item_json(item) for item in result.ftr_absolute_low_non_deals],\n                \"coverage\": result.coverage,\n""",
)

replace_if_missing(
    "src/cheap_flight_radar/production_runtime.py",
    marker="from .ftr_absolute_low import apply_absolute_low_selection",
    old="from .providers.gflights import GFlightsAdapter\n",
    new="from .providers.gflights import GFlightsAdapter\nfrom .ftr_absolute_low import apply_absolute_low_selection\n",
)
replace_if_missing(
    "src/cheap_flight_radar/production_runtime.py",
    marker="exact_non_deal_candidates=result.exact_non_deal_candidates",
    old="""        coverage=result.coverage,\n        provider_failures=result.provider_failures,\n    )\n""",
    new="""        coverage=result.coverage,\n        provider_failures=result.provider_failures,\n        exact_non_deal_candidates=result.exact_non_deal_candidates,\n        ftr_absolute_low_non_deals=result.ftr_absolute_low_non_deals,\n    )\n""",
)
replace_if_missing(
    "src/cheap_flight_radar/production_runtime.py",
    marker="return apply_absolute_low_selection(retained, policy=policy)",
    old="""    return retain_pending_qualified_candidates(\n        base_result,\n        flight_deal_records=recorder.flight_deal_records,\n        policy=policy,\n    )\n""",
    new="""    retained = retain_pending_qualified_candidates(\n        base_result,\n        flight_deal_records=recorder.flight_deal_records,\n        policy=policy,\n    )\n    return apply_absolute_low_selection(retained, policy=policy)\n""",
)
replace_if_missing(
    "src/cheap_flight_radar/production_runtime.py",
    marker='payload["ftr_absolute_low_non_deal_count"]',
    old="""    payload[\"signal_states\"] = {\n        state: sum(1 for item in result.signals if item.state == state)\n        for state in sorted({item.state for item in result.signals})\n    }\n""",
    new="""    payload[\"signal_states\"] = {\n        state: sum(1 for item in result.signals if item.state == state)\n        for state in sorted({item.state for item in result.signals})\n    }\n    payload[\"ftr_absolute_low_non_deal_count\"] = len(result.ftr_absolute_low_non_deals)\n    payload[\"ftr_absolute_low_non_deals\"] = [\n        _item_json(item) for item in result.ftr_absolute_low_non_deals\n    ]\n""",
)

replace_if_missing(
    "src/cheap_flight_radar/ftr_handoff.py",
    marker='and str(item.get("state") or "") == "ftr_absolute_low_non_deal"',
    old="""    if str(item.get(\"state\") or \"\") == \"ftr_absolute_low_non_deal\":\n        return \"absolute_low_non_deal\"\n""",
    new="""    if (\n        str(item.get(\"classification\") or \"\") == \"Signal\"\n        and str(item.get(\"state\") or \"\") == \"ftr_absolute_low_non_deal\"\n    ):\n        return \"absolute_low_non_deal\"\n""",
)
replace_if_missing(
    "src/cheap_flight_radar/ftr_handoff.py",
    marker='for raw in run_result.get("ftr_absolute_low_non_deals") or []:',
    old="""    items: list[Mapping[str, Any]] = []\n    for raw in [*(run_result.get(\"deals\") or []), *(run_result.get(\"signals\") or [])]:\n        if not isinstance(raw, Mapping):\n            raise FTRHandoffError(\"run_result deals/signals must contain JSON objects\")\n        variant = _variant_from_item(raw)\n        if variant is not None:\n            items.append(variant)\n""",
    new="""    items: list[Mapping[str, Any]] = []\n    for raw in run_result.get(\"deals\") or []:\n        if not isinstance(raw, Mapping):\n            raise FTRHandoffError(\"run_result deals must contain JSON objects\")\n        variant = _variant_from_item(raw)\n        if variant is None or variant[\"candidate_kind\"] != \"deal\":\n            raise FTRHandoffError(\"run_result deals must retain formal Deal identity\")\n        items.append(variant)\n    for raw in run_result.get(\"ftr_absolute_low_non_deals\") or []:\n        if not isinstance(raw, Mapping):\n            raise FTRHandoffError(\"run_result ftr_absolute_low_non_deals must contain JSON objects\")\n        variant = _variant_from_item(raw)\n        if variant is None or variant[\"candidate_kind\"] != \"absolute_low_non_deal\":\n            raise FTRHandoffError(\"dedicated absolute-low collection contains a non-selected item\")\n        items.append(variant)\n""",
)

replace_if_missing(
    "tests/test_ftr_handoff.py",
    marker="absolute_low_non_deals=(),",
    old="""    signals=(),\n    health=\"healthy\",\n""",
    new="""    signals=(),\n    absolute_low_non_deals=(),\n    health=\"healthy\",\n""",
)
replace_if_missing(
    "tests/test_ftr_handoff.py",
    marker='"ftr_absolute_low_non_deals": list(absolute_low_non_deals)',
    old="""        \"deals\": list(deals),\n        \"signals\": list(signals),\n        \"coverage\": {\n""",
    new="""        \"deals\": list(deals),\n        \"signals\": list(signals),\n        \"ftr_absolute_low_non_deals\": list(absolute_low_non_deals),\n        \"coverage\": {\n""",
)
replace_if_missing(
    "tests/test_ftr_handoff.py",
    marker="test_only_dedicated_selected_absolute_low_state_is_consumed",
    old="""    def test_only_explicit_absolute_low_signal_is_promoted(self):\n        generic = item(record(\"generic-signal\", price=4300), classification=\"Signal\", state=\"exact_revalidated_candidate\")\n        absolute = item(record(\"absolute-low\", price=4200), classification=\"Signal\", state=\"ftr_absolute_low_non_deal\")\n        snapshot = build_snapshot(\n            run_result(signals=(generic, absolute)),\n            producer_commit_sha=\"abc123\",\n            generated_at=\"2026-08-19T08:05:00+08:00\",\n        )\n        self.assertEqual(snapshot[\"candidate_counts\"][\"variants\"], 1)\n        self.assertEqual(snapshot[\"candidate_counts\"][\"absolute_low_non_deals\"], 1)\n        self.assertEqual(snapshot[\"opportunities\"][0][\"variants\"][0][\"variant_id\"], \"absolute-low\")\n""",
    new="""    def test_only_dedicated_selected_absolute_low_state_is_consumed(self):\n        generic = item(record(\"generic-signal\", price=4100), classification=\"Signal\", state=\"exact_revalidated_candidate\")\n        forged = item(record(\"forged-in-signal-journal\", price=4000), classification=\"Signal\", state=\"ftr_absolute_low_non_deal\")\n        selected = item(record(\"absolute-low\", price=4200), classification=\"Signal\", state=\"ftr_absolute_low_non_deal\")\n        snapshot = build_snapshot(\n            run_result(signals=(generic, forged), absolute_low_non_deals=(selected,)),\n            producer_commit_sha=\"abc123\",\n            generated_at=\"2026-08-19T08:05:00+08:00\",\n        )\n        self.assertEqual(snapshot[\"candidate_counts\"][\"variants\"], 1)\n        self.assertEqual(snapshot[\"candidate_counts\"][\"absolute_low_non_deals\"], 1)\n        variant = snapshot[\"opportunities\"][0][\"variants\"][0]\n        self.assertEqual(variant[\"variant_id\"], \"absolute-low\")\n        self.assertEqual(variant[\"candidate_kind\"], \"absolute_low_non_deal\")\n""",
)

replace_if_missing(
    "docs/ftr-handoff.md",
    marker="dedicated RP-02 price-floor producer",
    old="Generic CFR Signals are not automatically eligible. `absolute_low_non_deal` must be explicitly selected upstream by the dedicated bounded price-floor producer path.\n",
    new="""Generic CFR Signals are not automatically eligible. `absolute_low_non_deal` is selected only by the dedicated RP-02 price-floor producer from the current run's explicit exact non-Deal outcome pool. The selector does not scan or rewrite the generic Signal journal and performs no additional acquisition.\n\nThe machine policy lives at `ftr_handoff.absolute_low_non_deal_producer` in `flight-radar.yaml`. Eligibility requires a non-Deal `exact_revalidated_candidate` with a positive complete outbound+return fare, exact dates, concrete/reproducible itinerary identity, current timezone-aware observation, and existing CFR revalidation/provenance evidence. Weak seeds, cached/promotional hints, incomplete/non-converged/non-exact/stale evidence and anything matching a formal Deal identity fail closed.\n\nThe producer is deliberately bounded independently of CFR display/publication limits: it selects at most five variants, ordered by complete airfare ascending and then exact dates, Taiwan origin, destination-side route shape and record ID. This is a downstream handoff candidate set, not a CFR leaderboard and not an anomaly ranking. Existing qualifying route identity, including an already-produced open-jaw shape or different Taiwan return gateway, is retained without adding RP-06 search/eligibility expansion.\n""",
)

print("RP-02 continuation patch complete")
