"""Qualified anomaly-truth selection for formal Cheap Flight Radar Deals.

The product ranks formal Deals by relative anomaly first and current complete
airfare second.  This module deliberately selects one qualified truth source by
explicit priority; it never averages conflicting anomaly estimates.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Iterable, Sequence


@dataclass(frozen=True)
class AnomalyEvidence:
    """One source's anomaly claim for the same concrete airfare candidate."""

    source: str
    current_price_twd: float
    typical_price_twd: float | None = None
    discount_percent: float | None = None
    reproducible: bool = False
    qualified: bool = False
    evidence_kind: str = "external"

    def normalized_discount_percent(self) -> float | None:
        """Return positive percent below typical price, when the source supports it."""

        current = float(self.current_price_twd)
        if not isfinite(current) or current <= 0:
            return None

        if self.discount_percent is not None:
            discount = float(self.discount_percent)
            if isfinite(discount):
                return discount
            return None

        if self.typical_price_twd is None:
            return None
        typical = float(self.typical_price_twd)
        if not isfinite(typical) or typical <= 0:
            return None
        return (typical - current) / typical * 100.0

    def is_usable_truth(self) -> bool:
        """Whether this evidence can establish route-relative anomaly truth."""

        return self.qualified and self.reproducible and self.normalized_discount_percent() is not None


def select_anomaly_truth(
    evidences: Iterable[AnomalyEvidence],
    source_priority: Sequence[str],
) -> AnomalyEvidence | None:
    """Select the highest-priority qualified source; never combine estimates.

    Multiple observations from the same source are resolved deterministically by
    preferring stronger anomaly and then the lower current complete airfare.
    This tie-break is within one authority only; cross-source values are never
    averaged or blended.
    """

    usable = [evidence for evidence in evidences if evidence.is_usable_truth()]
    if not usable:
        return None

    by_source: dict[str, list[AnomalyEvidence]] = {}
    for evidence in usable:
        by_source.setdefault(evidence.source, []).append(evidence)

    for source in source_priority:
        candidates = by_source.get(source)
        if not candidates:
            continue
        return min(
            candidates,
            key=lambda item: (
                -float(item.normalized_discount_percent() or 0.0),
                float(item.current_price_twd),
            ),
        )
    return None


def formal_deal_sort_key(evidence: AnomalyEvidence) -> tuple[float, float]:
    """Sort key for formal Deals: anomaly descending, then complete airfare ascending."""

    if not evidence.is_usable_truth():
        raise ValueError("formal Deal ranking requires qualified reproducible anomaly truth")
    discount = evidence.normalized_discount_percent()
    assert discount is not None
    return (-discount, float(evidence.current_price_twd))
