"""FlyAI exact-date flight adapter.

The adapter consumes the tested official ``flyai search-flight`` CLI output. Runtime
credential configuration stays outside this module; the source router receives
credential/health state explicitly and this adapter never persists secrets.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from typing import Any

from ..models import (
    CollectorResult,
    FlightSegment,
    Journey,
    NormalizedOffer,
    SearchRequest,
)

CommandRunner = Callable[[Sequence[str], int], tuple[int, str, str]]


def default_runner(args: Sequence[str], timeout: int) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            list(args), capture_output=True, text=True, timeout=timeout, check=False
        )
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"
    except FileNotFoundError:
        return 127, "", "flyai executable not found"


def _journeys(item: Mapping[str, Any]) -> tuple[Journey, ...]:
    journeys: list[Journey] = []
    for journey in item.get("journeys") or []:
        segments: list[FlightSegment] = []
        for segment in journey.get("segments") or []:
            segments.append(
                FlightSegment(
                    origin=segment.get("depStationCode"),
                    destination=segment.get("arrStationCode"),
                    departure=segment.get("depDateTime"),
                    arrival=segment.get("arrDateTime"),
                    marketing_carrier=segment.get("marketingTransportName"),
                    marketing_flight_number=segment.get("marketingTransportNo"),
                    cabin=segment.get("seatClassName"),
                )
            )
        journeys.append(Journey(segments=tuple(segments)))
    return tuple(journeys)


def _is_exact_round_trip(offer: NormalizedOffer, request: SearchRequest) -> bool:
    if len(offer.journeys) < 2 or not request.return_date:
        return False
    outbound = offer.journeys[0].segments
    inbound = offer.journeys[1].segments
    if not outbound or not inbound:
        return False
    return (
        outbound[0].origin == request.origin
        and outbound[-1].destination == request.destination
        and str(outbound[0].departure or "")[:10] == request.outbound_date
        and inbound[0].origin == request.destination
        and inbound[-1].destination == request.origin
        and str(inbound[0].departure or "")[:10] == request.return_date
    )


class FlyAIAdapter:
    """Normalize FlyAI search output while rejecting airport/date substitutions."""

    provider = "flyai"

    def __init__(self, runner: CommandRunner = default_runner, timeout: int = 120):
        self.runner = runner
        self.timeout = timeout

    def collect(self, request: SearchRequest, observed_at: str) -> CollectorResult:
        if request.open_jaw_required or not request.return_date:
            return CollectorResult(
                provider=self.provider,
                health="ok",
                coverage_state="unsupported_query",
                error="current selected FlyAI production slice is exact round-trip only",
            )

        args = [
            "flyai",
            "search-flight",
            "--origin",
            request.origin,
            "--destination",
            request.destination,
            "--dep-date",
            request.outbound_date,
            "--back-date",
            request.return_date,
            "--seat-class-name",
            "economy",
            "--sort-type",
            "3",
        ]
        code, stdout, stderr = self.runner(args, self.timeout)
        if code != 0:
            return CollectorResult(
                provider=self.provider,
                health="failed",
                coverage_state="failed",
                error=f"command_exit={code}; {stderr[-300:]}",
            )

        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            return CollectorResult(
                provider=self.provider,
                health="failed",
                coverage_state="failed",
                error="invalid_json",
            )

        if payload.get("status") != 0:
            return CollectorResult(
                provider=self.provider,
                health="failed",
                coverage_state="failed",
                error=(
                    f"provider_status={payload.get('status')}; "
                    f"message={payload.get('message')}"
                ),
            )

        raw_items = (((payload.get("data") or {}).get("itemList")) or [])
        if not isinstance(raw_items, list):
            return CollectorResult(
                provider=self.provider,
                health="failed",
                coverage_state="failed",
                error="invalid_item_list",
            )

        normalized: list[NormalizedOffer] = []
        for item in raw_items:
            if not isinstance(item, Mapping):
                continue
            offer = NormalizedOffer(
                provider=self.provider,
                search_stage=request.search_stage,
                profile=request.profile,
                requested_origin=request.origin,
                requested_destination=request.destination,
                journeys=_journeys(item),
                source_id=None,
                source_url=(
                    item.get("jumpUrl") or item.get("jumpURL") or item.get("url")
                ),
                raw_price=item.get("ticketPrice"),
                original_currency=None,
                tax_semantics="unknown",
                fare_family=None,
                baggage_state="unknown",
                freshness="provider_live_search",
                verification_state="discovery",
                observed_at=observed_at,
                exact_airport_date=False,
            )
            normalized.append(
                replace(
                    offer,
                    exact_airport_date=_is_exact_round_trip(offer, request),
                )
            )

        exact = tuple(offer for offer in normalized if offer.exact_airport_date)
        return CollectorResult(
            provider=self.provider,
            health="ok",
            coverage_state="exact_results" if exact else "no_exact_result",
            offers=exact,
            returned_items=len(normalized),
            rejected_items=len(normalized) - len(exact),
        )
