"""Targeted one-shot introspection for Kiwi multi-city GraphQL types.

Experiment-only. One direct request, fixed CFR UA, no credentials/cookies,
proxy, retry, session mutation, browser impersonation, or rate-limit reset.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

ENDPOINT = "https://api.skypicker.com/umbrella/v2/graphql"
USER_AGENT = "CheapFlightRadar/0.1 (+public-research; no-proxy)"
TYPE = "kind name ofType { kind name ofType { kind name ofType { kind name } } }"
QUERY = f"""
query CFRMultiCityTypeProbe {{
  queryType: __type(name: "Query") {{
    fields {{ name args {{ name type {{ {TYPE} }} }} type {{ {TYPE} }} }}
  }}
  search: __type(name: "SearchMulticityInput") {{
    inputFields {{ name type {{ {TYPE} }} }}
  }}
  itineraryInput: __type(name: "ItineraryMulticityInput") {{
    inputFields {{ name type {{ {TYPE} }} }}
  }}
  itineraryOutput: __type(name: "ItineraryMulticity") {{
    fields {{ name type {{ {TYPE} }} }}
  }}
  itineraries: __type(name: "Itineraries") {{
    fields {{ name type {{ {TYPE} }} }}
  }}
  sector: __type(name: "Sector") {{
    fields {{ name type {{ {TYPE} }} }}
  }}
  segment: __type(name: "Segment") {{
    fields {{ name type {{ {TYPE} }} }}
  }}
  bookingOptions: __type(name: "BookingOptionConnection") {{
    fields {{ name type {{ {TYPE} }} }}
  }}
}}
"""


def signature(node: dict | None) -> str:
    if not node:
        return "?"
    kind = node.get("kind")
    if kind == "NON_NULL":
        return signature(node.get("ofType")) + "!"
    if kind == "LIST":
        return "[" + signature(node.get("ofType")) + "]"
    return str(node.get("name") or kind or "?")


def fields(item: dict | None, key: str) -> list[dict[str, str]]:
    return [
        {"name": row.get("name"), "type": signature(row.get("type"))}
        for row in (item or {}).get(key) or []
    ]


def main() -> int:
    body = json.dumps({"query": QUERY, "operationName": "CFRMultiCityTypeProbe"}).encode()
    request = urllib.request.Request(
        ENDPOINT,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            document = json.loads(response.read())
            status = int(response.status)
    except urllib.error.HTTPError as exc:
        print(json.dumps({"http_status": exc.code, "request_count": 1, "failure": "http_error", "body_prefix": exc.read().decode(errors="replace")[:1200]}, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"request_count": 1, "failure": f"{type(exc).__name__}: {exc}"}, indent=2))
        return 0

    data = document.get("data") or {}
    multi_query = None
    for row in (data.get("queryType") or {}).get("fields") or []:
        if row.get("name") == "multicityItineraries":
            multi_query = {
                "name": row.get("name"),
                "type": signature(row.get("type")),
                "args": [{"name": arg.get("name"), "type": signature(arg.get("type"))} for arg in row.get("args") or []],
            }
            break
    result = {
        "endpoint": ENDPOINT,
        "http_status": status,
        "request_count": 1,
        "graphql_errors": document.get("errors"),
        "multicity_query": multi_query,
        "SearchMulticityInput": fields(data.get("search"), "inputFields"),
        "ItineraryMulticityInput": fields(data.get("itineraryInput"), "inputFields"),
        "ItineraryMulticity": fields(data.get("itineraryOutput"), "fields"),
        "Itineraries": fields(data.get("itineraries"), "fields"),
        "Sector": fields(data.get("sector"), "fields"),
        "Segment": fields(data.get("segment"), "fields"),
        "BookingOptionConnection": fields(data.get("bookingOptions"), "fields"),
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
