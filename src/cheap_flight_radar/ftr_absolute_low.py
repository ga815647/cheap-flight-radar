"""Dedicated bounded absolute-low non-Deal selector for FTR handoff.

The selector consumes only the current run's explicit exact non-Deal outcome
pool. It never scans or rewrites the generic CFR Signal journal, performs no
provider acquisition, and does not participate in CFR Deal ranking.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Mapping, Sequence

from .airfare import AirfareRecord, is_international_asia_oceania
from .models import TAIWAN_MAIN_ISLAND_PUBLIC_PASSENGER_AIRPORTS
from .production_radar import RadarItem, RadarRunResult


OUTPUT_STATE = "ftr_absolute_low_non_deal"
SUPPORTED_CONTRACT_VERSION = "1.0"
SUPPORTED_INPUT_STATES = ("exact_revalidated_candidate",)
SUPPORTED_ORDERING = (
    "current_complete_airfare_twd_asc",
    "outbound_date_asc",
    "return_date_asc",
    "taiwan_origin_gateway_asc",
    "destination_arrival_airport_asc",
    "destination_departure_airport_asc",
    "record_id_asc",
)


class FTRAbsoluteLowPolicyError(ValueError):
    """Raised when the machine SSOT does not match the selector contract."""


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def validate_absolute_low_policy(policy: Mapping[str, Any]) -> Mapping[str, Any]:
    """Fail closed if the machine SSOT drifts from the implemented contract."""
    ftr = _mapping(policy.get("ftr_handoff"))
    producer = _mapping(ftr.get("absolute_low_non_deal_producer"))
    if not producer:
        raise FTRAbsoluteLowPolicyError("missing ftr_handoff.absolute_low_non_deal_producer policy")
    if producer.get("enabled") is not True:
        raise FTRAbsoluteLowPolicyError("absolute-low producer must be explicitly enabled")
    if str(producer.get("contract_version") or "") != SUPPORTED_CONTRACT_VERSION:
        raise FTRAbsoluteLowPolicyError("absolute-low producer contract_version is unsupported")
    if str(producer.get("output_state") or "") != OUTPUT_STATE:
        raise FTRAbsoluteLowPolicyError("absolute-low producer output_state drifted")
    if str(producer.get("contract_state") or "") != "implemented_pre_activation":
        raise FTRAbsoluteLowPolicyError("absolute-low producer contract_state drifted")
    if str(producer.get("source_collection") or "") != "current_run_exact_non_deal_candidates":
        raise FTRAbsoluteLowPolicyError("absolute-low producer source_collection drifted")
    if tuple(str(value) for value in (producer.get("input_states") or ())) != SUPPORTED_INPUT_STATES:
        raise FTRAbsoluteLowPolicyError("absolute-low producer input_states drifted")
    if tuple(str(value) for value in (producer.get("ordering") or ())) != SUPPORTED_ORDERING:
        raise FTRAbsoluteLowPolicyError("absolute-low producer ordering drifted")
    budget = _mapping(producer.get("budget"))
    limit = budget.get("max_selected_count")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise FTRAbsoluteLowPolicyError("absolute-low max_selected_count must be a positive integer")
    if budget.get("independent_of_search_final_shortlist_limit") is not True:
        raise FTRAbsoluteLowPolicyError("absolute-low budget must remain independent of search shortlist")
    if budget.get("independent_of_publication_display_limits") is not True:
        raise FTRAbsoluteLowPolicyError("absolute-low budget must remain independent of publication limits")
    if budget.get("new_provider_calls") != 0:
        raise FTRAbsoluteLowPolicyError("absolute-low producer must not add provider calls")
    eligibility = _mapping(producer.get("eligibility"))
    max_age = eligibility.get("max_observation_age_hours")
    if isinstance(max_age, bool) or not isinstance(max_age, int) or max_age <= 0:
        raise FTRAbsoluteLowPolicyError("absolute-low max_observation_age_hours must be a positive integer")
    if str(eligibility.get("verification_state") or "") != "revalidated":
        raise FTRAbsoluteLowPolicyError("absolute-low verification_state must remain revalidated")
    if str(eligibility.get("evidence_class") or "") != "exact_revalidated_candidate":
        raise FTRAbsoluteLowPolicyError("absolute-low evidence_class must remain exact_revalidated_candidate")
    if tuple(str(value) for value in (eligibility.get("allowed_surfaces") or ())) != ("exact", "open_jaw"):
        raise FTRAbsoluteLowPolicyError("absolute-low allowed_surfaces drifted")
    required_eligibility_flags = (
        "require_non_deal",
        "require_exact_record",
        "require_complete_outbound_return_airfare",
        "require_positive_complete_airfare_twd",
        "require_exact_outbound_and_return_dates",
        "require_concrete_itinerary_identity",
        "require_reproducible_search_identity",
        "require_source_evidence_provenance",
        "require_existing_cfr_revalidation_trust",
        "require_current_observation",
    )
    if any(eligibility.get(field) is not True for field in required_eligibility_flags):
        raise FTRAbsoluteLowPolicyError("absolute-low required eligibility flags drifted")
    if tuple(str(value) for value in (eligibility.get("trusted_evidence_any_of") or ())) != (
        "booking_url",
        "evidence_url",
        "booking_token",
        "provider_leg_identity",
    ):
        raise FTRAbsoluteLowPolicyError("absolute-low trusted evidence contract drifted")
    isolation = _mapping(producer.get("generic_signal_isolation"))
    if isolation.get("generic_signal_collection_is_not_selector_input") is not True:
        raise FTRAbsoluteLowPolicyError("generic Signal isolation must remain enabled")
    if isolation.get("classification_signal_alone_is_ineligible") is not True:
        raise FTRAbsoluteLowPolicyError("Signal classification alone must remain ineligible")
    if isolation.get("weak_seed_promotion") != "forbidden":
        raise FTRAbsoluteLowPolicyError("weak-seed promotion must remain forbidden")
    if isolation.get("cached_or_promotional_hint_promotion") != "forbidden":
        raise FTRAbsoluteLowPolicyError("cached/promotional hint promotion must remain forbidden")
    deal_isolation = _mapping(producer.get("deal_isolation"))
    if deal_isolation.get("formal_deal_input") != "excluded":
        raise FTRAbsoluteLowPolicyError("formal Deal input must remain excluded")
    if deal_isolation.get("matching_deal_record_or_itinerary") != "excluded":
        raise FTRAbsoluteLowPolicyError("matching Deal identity must remain excluded")
    if deal_isolation.get("formal_deal_relabel_or_duplicate") != "forbidden":
        raise FTRAbsoluteLowPolicyError("formal Deal relabel/duplicate must remain forbidden")
    if str(producer.get("anomaly_ranking_role") or "") != "none":
        raise FTRAbsoluteLowPolicyError("absolute-low producer must not become anomaly ranking")
    if str(producer.get("ftr_weighted_score") or "") != "forbidden":
        raise FTRAbsoluteLowPolicyError("FTR weighted score must remain forbidden")
    if producer.get("normal_cfr_deal_ranking_unchanged") is not True:
        raise FTRAbsoluteLowPolicyError("normal CFR Deal ranking must remain unchanged")
    if producer.get("preserve_existing_route_identity") is not True:
        raise FTRAbsoluteLowPolicyError("existing route identity preservation drifted")
    if str(producer.get("rp06_new_open_jaw_or_return_gateway_acquisition") or "") != "out_of_scope":
        raise FTRAbsoluteLowPolicyError("RP-06 acquisition boundary drifted")
    if str(producer.get("canonical_ftr_activation") or "") != "pending_disabled_until_RP-04":
        raise FTRAbsoluteLowPolicyError("canonical FTR activation boundary drifted")
    canonical = _mapping(ftr.get("canonical_activation"))
    if canonical.get("enabled") is not False:
        raise FTRAbsoluteLowPolicyError("RP-02 must not activate canonical FTR runtime")
    return producer


def _aware_datetime(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _exact_dates(record: AirfareRecord) -> tuple[str, str] | None:
    outbound = record.outbound_date
    returned = record.return_date
    if not outbound or not returned:
        return None
    try:
        outbound_date = date.fromisoformat(outbound)
        return_date = date.fromisoformat(returned)
    except ValueError:
        return None
    if return_date <= outbound_date:
        return None
    return outbound, returned


def _destination_departure(record: AirfareRecord) -> str:
    if record.surface == "open_jaw" and len(record.legs) >= 2:
        return record.legs[-1].origin
    return record.destination.iata


def _taiwan_return_gateway(record: AirfareRecord) -> str:
    if record.surface == "open_jaw" and len(record.legs) >= 2:
        return record.legs[-1].destination
    return record.origin.iata


def _reproducible_identity(record: AirfareRecord) -> bool:
    search = _mapping(record.reproducible_search)
    if record.surface == "exact":
        return bool(
            str(search.get("origin") or "") == record.origin.iata
            and str(search.get("destination") or "") == record.destination.iata
            and str(search.get("date") or "") == str(record.outbound_date or "")
            and str(search.get("return_date") or "") == str(record.return_date or "")
        )
    if record.surface == "open_jaw":
        raw_legs = search.get("legs")
        if not isinstance(raw_legs, Sequence) or isinstance(raw_legs, (str, bytes)) or len(raw_legs) < 2:
            return False
        normalized = [(leg.origin, leg.destination, leg.date) for leg in record.legs]
        observed = []
        for raw in raw_legs:
            if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)) or len(raw) != 3:
                return False
            observed.append(tuple(str(value) for value in raw))
        return tuple(observed) == tuple(normalized)
    return False


def _trust_provenance(record: AirfareRecord) -> bool:
    return bool(
        record.provider
        and record.observed_at
        and record.reproducible_search
        and (
            record.booking_url
            or record.evidence_url
            or record.booking_token
            or record.has_provider_leg_identity
        )
    )


def _identity(record: AirfareRecord) -> tuple[Any, ...]:
    dates = _exact_dates(record) or ("", "")
    return (
        record.origin.iata,
        record.destination.iata,
        _destination_departure(record),
        _taiwan_return_gateway(record),
        dates[0],
        dates[1],
        tuple(
            (leg.origin, leg.destination, leg.date, leg.departure_time, leg.arrival_time)
            for leg in record.legs
        ),
    )


def _sort_key(item: RadarItem) -> tuple[Any, ...]:
    exact = item.exact
    if exact is None:
        return (10**18, "", "", "", "", "", "")
    dates = _exact_dates(exact) or ("", "")
    return (
        int(exact.current_price_twd or 10**18),
        dates[0],
        dates[1],
        exact.origin.iata,
        exact.destination.iata,
        _destination_departure(exact),
        exact.record_id,
    )


def _eligible(
    item: RadarItem,
    *,
    run_at: datetime,
    policy: Mapping[str, Any],
    input_states: tuple[str, ...],
) -> bool:
    if item.classification != "Signal" or item.state not in input_states:
        return False
    exact = item.exact
    if exact is None:
        return False
    eligibility = _mapping(policy.get("eligibility"))
    if exact.verification_state != str(eligibility.get("verification_state")):
        return False
    if exact.evidence_class != str(eligibility.get("evidence_class")):
        return False
    if exact.surface not in tuple(str(value) for value in (eligibility.get("allowed_surfaces") or ())):
        return False
    if not exact.complete_airfare or not exact.current_price_twd or exact.current_price_twd <= 0:
        return False
    if _exact_dates(exact) is None or not exact.record_id or not exact.legs:
        return False
    if exact.origin.iata not in {str(value) for value in policy_root_search(policy).get("origin_airports", ())}:
        return False
    if _taiwan_return_gateway(exact) not in TAIWAN_MAIN_ISLAND_PUBLIC_PASSENGER_AIRPORTS:
        return False
    if not is_international_asia_oceania(item.discovery.destination.country):
        return False
    if not item.observation_id:
        return False
    if not _reproducible_identity(exact) or not _trust_provenance(exact):
        return False
    observed_at = _aware_datetime(exact.observed_at)
    if observed_at is None:
        return False
    max_age = int(eligibility["max_observation_age_hours"])
    delta_hours = abs((run_at - observed_at).total_seconds()) / 3600.0
    if delta_hours > max_age:
        return False
    return True


def policy_root_search(producer_policy: Mapping[str, Any]) -> Mapping[str, Any]:
    root = producer_policy.get("_root_policy")
    return _mapping(_mapping(root).get("search"))


def select_absolute_low_non_deals(
    result: RadarRunResult,
    *,
    policy: Mapping[str, Any],
) -> tuple[RadarItem, ...]:
    """Select a bounded price-first set from explicit exact non-Deal outcomes."""
    producer = dict(validate_absolute_low_policy(policy))
    producer["_root_policy"] = policy
    run_at = _aware_datetime(result.run_at)
    if run_at is None:
        raise ValueError("RadarRunResult.run_at must be timezone-aware ISO-8601")

    deal_record_ids = {
        item.exact.record_id
        for item in result.deals
        if item.exact is not None
    }
    deal_observation_ids = {
        item.observation_id
        for item in result.deals
        if item.observation_id
    }
    deal_identities = {
        _identity(item.exact)
        for item in result.deals
        if item.exact is not None
    }

    eligible: list[RadarItem] = []
    for item in result.exact_non_deal_candidates:
        if not _eligible(
            item,
            run_at=run_at,
            policy=producer,
            input_states=SUPPORTED_INPUT_STATES,
        ):
            continue
        assert item.exact is not None
        if (
            item.exact.record_id in deal_record_ids
            or item.observation_id in deal_observation_ids
            or _identity(item.exact) in deal_identities
        ):
            continue
        eligible.append(item)

    eligible.sort(key=_sort_key)
    deduped: list[RadarItem] = []
    seen_record_ids: set[str] = set()
    seen_identities: set[tuple[Any, ...]] = set()
    for item in eligible:
        assert item.exact is not None
        identity = _identity(item.exact)
        if item.exact.record_id in seen_record_ids or identity in seen_identities:
            continue
        seen_record_ids.add(item.exact.record_id)
        seen_identities.add(identity)
        deduped.append(item)

    limit = int(_mapping(producer.get("budget"))["max_selected_count"])
    return tuple(
        RadarItem(
            classification="Signal",
            state=OUTPUT_STATE,
            discovery=item.discovery,
            exact=item.exact,
            anomaly_source=item.anomaly_source,
            anomaly_strength_percent=item.anomaly_strength_percent,
            reason="selected by dedicated bounded FTR absolute-low non-Deal producer from current exact/revalidated evidence",
            observation_id=item.observation_id,
            anomaly_baseline_twd=item.anomaly_baseline_twd,
            anomaly_scope=item.anomaly_scope,
        )
        for item in deduped[:limit]
    )


def apply_absolute_low_selection(
    result: RadarRunResult,
    *,
    policy: Mapping[str, Any],
) -> RadarRunResult:
    selected = select_absolute_low_non_deals(result, policy=policy)
    return RadarRunResult(
        radar_run_id=result.radar_run_id,
        run_at=result.run_at,
        deals=result.deals,
        signals=result.signals,
        coverage=result.coverage,
        provider_failures=result.provider_failures,
        exact_non_deal_candidates=result.exact_non_deal_candidates,
        ftr_absolute_low_non_deals=selected,
    )
