"""Typed CFR access-blind-spot coverage evidence.

Blind spots describe known access limitations.  They never manufacture a
hidden fare, price, route, date or formal candidate.  The initial registry
is policy-backed static evidence; future collectors may add observations
only after preserving the same typed distinctions.
"""
from __future__ import annotations

from typing import Any, Mapping


VALID_FARE_EXISTENCE = frozenset({"known_exists", "unknown"})
VALID_SURFACE_CLASS_EXISTENCE = frozenset({"known", "unknown"})
VALID_VISIBILITY = frozenset({"public", "restricted", "unknown"})
VALID_ACCESS = frozenset({"available", "unavailable", "unknown"})
VALID_TRUTH = frozenset({"eligible", "ineligible", "unknown"})
VALID_PRICE_OBSERVABILITY = frozenset({"available", "unavailable", "unknown"})
FORBIDDEN_HIDDEN_PRICE_KEYS = frozenset({
    "price", "price_twd", "fare", "fare_twd", "amount", "current_price_twd",
    "typical_price_twd", "discount_percent",
})


class AccessBlindSpotError(ValueError):
    """Raised when blind-spot evidence would blur or fabricate access truth."""


def _enum(item: Mapping[str, Any], key: str, allowed: frozenset[str]) -> str:
    value = str(item.get(key) or "")
    if value not in allowed:
        raise AccessBlindSpotError(f"{key} must be one of {sorted(allowed)}")
    return value


def normalize_access_blind_spots(policy: Mapping[str, Any]) -> Mapping[str, Any]:
    config = policy.get("access_blind_spots") or {}
    schema_version = int(config.get("schema_version", 0))
    if schema_version != 1:
        raise AccessBlindSpotError("access_blind_spots.schema_version must be 1")
    registry = config.get("registry") or []
    if not isinstance(registry, list):
        raise AccessBlindSpotError("access_blind_spots.registry must be a list")

    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in registry:
        if not isinstance(raw, Mapping):
            raise AccessBlindSpotError("blind-spot registry entries must be mappings")
        spot_id = str(raw.get("id") or "")
        if not spot_id or spot_id in seen:
            raise AccessBlindSpotError("blind-spot id must be unique and non-empty")
        seen.add(spot_id)
        forbidden = FORBIDDEN_HIDDEN_PRICE_KEYS.intersection(raw)
        if forbidden:
            raise AccessBlindSpotError(
                f"blind spot {spot_id} must not contain hidden fare/price fields: {sorted(forbidden)}"
            )
        source_class = str(raw.get("source_class") or "")
        access_gate = str(raw.get("access_gate") or "")
        evidence_reference = str(raw.get("evidence_reference") or "")
        if not source_class or not access_gate or not evidence_reference:
            raise AccessBlindSpotError(
                f"blind spot {spot_id} requires source_class, access_gate and evidence_reference"
            )
        item = {
            "id": spot_id,
            "source_class": source_class,
            "surface_class_existence": _enum(raw, "surface_class_existence", VALID_SURFACE_CLASS_EXISTENCE),
            "specific_fare_existence": _enum(raw, "specific_fare_existence", VALID_FARE_EXISTENCE),
            "visibility": _enum(raw, "visibility", VALID_VISIBILITY),
            "access_gate": access_gate,
            "automatic_observation": _enum(raw, "automatic_observation", VALID_ACCESS),
            "exact_reproducibility": _enum(raw, "exact_reproducibility", VALID_ACCESS),
            "formal_truth_eligibility": _enum(raw, "formal_truth_eligibility", VALID_TRUTH),
            "price_observability": _enum(raw, "price_observability", VALID_PRICE_OBSERVABILITY),
            "evidence_reference": evidence_reference,
            "coverage_semantics": str(raw.get("coverage_semantics") or "known_access_blind_spot_not_market_absence"),
        }
        if (
            item["price_observability"] != "available"
            and item["formal_truth_eligibility"] == "eligible"
        ):
            raise AccessBlindSpotError(
                f"blind spot {spot_id} cannot be formal truth when exact price is not observable"
            )
        if (
            item["specific_fare_existence"] == "unknown"
            and item["coverage_semantics"] == "fare_exists"
        ):
            raise AccessBlindSpotError(
                f"blind spot {spot_id} cannot claim fare existence while existence is unknown"
            )
        normalized.append(item)

    normalized.sort(key=lambda item: item["id"])
    return {
        "schema_version": 1,
        "health_role": "informational_non_required",
        "affects_provider_health": False,
        "items": normalized,
    }
