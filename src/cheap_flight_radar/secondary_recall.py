"""Composite adapter for bounded opportunistic endpoint recall."""
from __future__ import annotations

from typing import Any, Sequence

from .airfare import AirfareRecord, ProviderResult


class SecondaryRecallAdapter:
    """Merge orchestrator-supplied weak endpoint evidence into recall results.

    Records retain their original provider/surface/provenance. They do not gain
    anomaly authority here; ProductionRadar still performs bounded flexible and
    exact completion before any formal Deal can emerge.
    """

    def __init__(self, delegate: Any, records: Sequence[AirfareRecord] = ()) -> None:
        self._delegate = delegate
        self.records = tuple(records)
        self._by_origin: dict[str, tuple[AirfareRecord, ...]] = {
            origin: tuple(item for item in self.records if item.origin.iata == origin)
            for origin in {item.origin.iata for item in self.records}
        }

    async def explore(self, *, origin: str, **kwargs: Any) -> ProviderResult:
        primary = await self._delegate.explore(origin=origin, **kwargs)
        extras = self._by_origin.get(origin, ())
        if not extras:
            return primary
        if primary.coverage_state == "failed":
            return ProviderResult("secondary_recall", "explore_secondary", "complete", extras, error=primary.error)
        return ProviderResult(
            primary.provider,
            "explore_secondary",
            primary.coverage_state,
            tuple([*primary.records, *extras]),
            error=primary.error,
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)
