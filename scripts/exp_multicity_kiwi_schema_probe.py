"""One-shot live Kiwi multi-city fare proof for a real CFR open-jaw shape.

Experiment-only. One direct request, fixed CFR UA, no credentials/cookies,
proxy, retry, session mutation, browser impersonation, or rate-limit reset.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

ENDPOINT = "https://api.skypicker.com/umbrella/v2/graphql?featureName=SearchMulticityItinerariesQuery"
USER_AGENT = "CheapFlightRadar/0.1 (+public-research; no-proxy)"
REQUESTED_LEGS = [
    ("KHH", "DRP", "2026-10-11"),
    ("ILO", "KHH", "2026-10-19"),
]

QUERY = r"""
query SearchMulticityItinerariesQuery(
  $search: SearchMulticityInput
  $filter: ItinerariesFilterInput
  $options: ItinerariesOptionsInput
) {
  multicityItineraries(search: $search, filter: $filter, options: $options) {
    __typename
    ... on AppError {
      error: message
    }
    ... on Itineraries {
      itineraries {
        __typename
        ... on ItineraryMulticity {
          id
          price { amount }
          priceEur { amount }
          sectors {
            duration
            sectorSegments {
              segment {
                code
                type
                source {
                  localTime
                  station { code name }
                }
                destination {
                  localTime
                  station { code name }
                }
                carrier { code name }
              }
            }
          }
          bookingOptions {
            edges { node { bookingUrl } }
          }
        }
      }
    }
  }
}
"""


def leg(origin: str, destination: str, date: str) -> dict:
    return {
        "source": {"ids": [origin]},
        "destination": {"ids": [destination]},
        "outboundDepartureDate": {
            "start": f"{date}T00:00:00",
            "end": f"{date}T23:59:59",
        },
    }


def summarize_sector(sector: dict) -> dict:
    segments = []
    for row in sector.get("sectorSegments") or []:
        segment = (row or {}).get("segment") or {}
        source = segment.get("source") or {}
        destination = segment.get("destination") or {}
        carrier = segment.get("carrier") or {}
        segments.append({
            "flight": segment.get("code"),
            "carrier": carrier.get("code"),
            "origin": (source.get("station") or {}).get("code"),
            "destination": (destination.get("station") or {}).get("code"),
            "departure_local": source.get("localTime"),
            "arrival_local": destination.get("localTime"),
        })
    return {"duration": sector.get("duration"), "segments": segments}


def main() -> int:
    variables = {
        "search": {
            "itinerary": [leg(*item) for item in REQUESTED_LEGS],
            "passengers": {"adults": 1},
            "cabinClass": {"cabinClass": "ECONOMY", "applyMixedClasses": False},
        },
        "filter": {
            "allowChangeInboundDestination": False,
            "allowChangeInboundSource": False,
            "allowDifferentStationConnection": True,
            "enableSelfTransfer": True,
            "enableThrowAwayTicketing": False,
            "enableTrueHiddenCity": False,
            "transportTypes": ["FLIGHT"],
            "contentProviders": ["KIWI", "FRESH", "KAYAK"],
            "flightsApiLimit": 10,
            "limit": 10,
            "maxStopsCount": 2,
        },
        "options": {
            "sortBy": "PRICE",
            "mergePriceDiffRule": "INCREASED",
            "currency": "twd",
            "locale": "en",
            "partner": "skypicker",
            "affilID": "skypicker",
            "storeSearch": False,
            "searchStrategy": "REDUCED",
        },
    }
    body = json.dumps({
        "query": QUERY,
        "variables": variables,
        "operationName": "SearchMulticityItinerariesQuery",
    }).encode()
    request = urllib.request.Request(
        ENDPOINT,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            document = json.loads(response.read())
            status = int(response.status)
    except urllib.error.HTTPError as exc:
        print(json.dumps({
            "http_status": exc.code,
            "request_count": 1,
            "qualified": False,
            "requested_legs": REQUESTED_LEGS,
            "failure": "http_error",
            "body_prefix": exc.read().decode(errors="replace")[:1600],
        }, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({
            "request_count": 1,
            "qualified": False,
            "requested_legs": REQUESTED_LEGS,
            "failure": f"{type(exc).__name__}: {exc}",
        }, indent=2))
        return 0

    result = (document.get("data") or {}).get("multicityItineraries") or {}
    rows = result.get("itineraries") or []
    candidates = []
    for row in rows:
        if row.get("__typename") != "ItineraryMulticity":
            continue
        try:
            price = int((row.get("price") or {}).get("amount"))
        except (TypeError, ValueError):
            continue
        if price <= 0:
            continue
        booking_urls = [
            ((edge or {}).get("node") or {}).get("bookingUrl")
            for edge in ((row.get("bookingOptions") or {}).get("edges") or [])
        ]
        booking_urls = [url for url in booking_urls if url]
        sectors = [summarize_sector(sector or {}) for sector in row.get("sectors") or []]
        candidates.append({
            "id": row.get("id"),
            "price_twd": price,
            "price_eur": (row.get("priceEur") or {}).get("amount"),
            "booking_url": booking_urls[0] if booking_urls else None,
            "sectors": sectors,
        })

    candidates.sort(key=lambda item: item["price_twd"])
    cheapest = candidates[0] if candidates else None
    exact_shape = False
    if cheapest and len(cheapest["sectors"]) == len(REQUESTED_LEGS):
        observed = []
        for sector in cheapest["sectors"]:
            segments = sector.get("segments") or []
            if not segments:
                observed.append((None, None, None))
                continue
            first, last = segments[0], segments[-1]
            departure = str(first.get("departure_local") or "")[:10]
            observed.append((first.get("origin"), last.get("destination"), departure))
        exact_shape = observed == REQUESTED_LEGS

    print(json.dumps({
        "endpoint": ENDPOINT,
        "http_status": status,
        "request_count": 1,
        "graphql_errors": document.get("errors"),
        "result_typename": result.get("__typename"),
        "provider_error": result.get("error"),
        "requested_legs": REQUESTED_LEGS,
        "returned_multicity_count": len(candidates),
        "exact_shape": exact_shape,
        "complete_airfare": bool(cheapest and cheapest.get("price_twd") and cheapest.get("booking_url") and exact_shape),
        "qualified": bool(cheapest and cheapest.get("price_twd") and cheapest.get("booking_url") and exact_shape),
        "cheapest": cheapest,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
