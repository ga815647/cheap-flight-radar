"""One-shot research probe for a safe Kiwi consumer GraphQL multi-city contract.

Experiment-only. Uses one direct HTTP request, one fixed CFR user agent, no
credential/cookie/proxy/retry/session mutation, and prints only schema names
relevant to multi-city capability qualification.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

ENDPOINT = "https://api.skypicker.com/umbrella/v2/graphql"
USER_AGENT = "CheapFlightRadar/0.1 (+public-research; no-proxy)"

QUERY = r"""
query CFRMultiCityCapabilityProbe {
  __schema {
    queryType {
      fields {
        name
        args {
          name
          type {
            kind
            name
            ofType { kind name ofType { kind name } }
          }
        }
      }
    }
    types {
      kind
      name
      inputFields {
        name
        type {
          kind
          name
          ofType { kind name ofType { kind name } }
        }
      }
    }
  }
}
"""


def _type_name(node: dict | None) -> str | None:
    while isinstance(node, dict):
        name = node.get("name")
        if name:
            return str(name)
        node = node.get("ofType")
    return None


def main() -> int:
    payload = json.dumps({"query": QUERY, "operationName": "CFRMultiCityCapabilityProbe"}).encode()
    request = urllib.request.Request(
        ENDPOINT,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            status = int(response.status)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(json.dumps({
            "endpoint": ENDPOINT,
            "http_status": exc.code,
            "request_count": 1,
            "multi_city_contract_exposed": False,
            "failure": "http_error",
            "body_prefix": body[:1200],
        }, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({
            "endpoint": ENDPOINT,
            "request_count": 1,
            "multi_city_contract_exposed": False,
            "failure": f"{type(exc).__name__}: {exc}",
        }, indent=2, sort_keys=True))
        return 0

    try:
        document = json.loads(raw)
    except json.JSONDecodeError:
        print(json.dumps({
            "endpoint": ENDPOINT,
            "http_status": status,
            "request_count": 1,
            "multi_city_contract_exposed": False,
            "failure": "non_json_response",
            "body_prefix": raw[:1200].decode("utf-8", errors="replace"),
        }, indent=2, sort_keys=True))
        return 0

    schema = ((document.get("data") or {}).get("__schema") or {})
    query_fields = ((schema.get("queryType") or {}).get("fields") or [])
    types = schema.get("types") or []
    needles = ("multi", "nomad", "itinerar", "route")

    candidate_queries = []
    for field in query_fields:
        name = str(field.get("name") or "")
        args = [
            {"name": arg.get("name"), "type": _type_name(arg.get("type"))}
            for arg in field.get("args") or []
        ]
        haystack = " ".join([name, *(str(arg.get("type") or "") for arg in args)]).lower()
        if any(needle in haystack for needle in needles):
            candidate_queries.append({"name": name, "args": args})

    candidate_inputs = []
    for item in types:
        if item.get("kind") != "INPUT_OBJECT":
            continue
        name = str(item.get("name") or "")
        fields = [
            {"name": fld.get("name"), "type": _type_name(fld.get("type"))}
            for fld in item.get("inputFields") or []
        ]
        haystack = " ".join([name, *(str(fld.get("name") or "") for fld in fields)]).lower()
        if any(needle in haystack for needle in needles):
            candidate_inputs.append({"name": name, "fields": fields})

    exposed = any(
        "multi" in str(item.get("name", "")).lower() or "nomad" in str(item.get("name", "")).lower()
        for item in [*candidate_queries, *candidate_inputs]
    )
    print(json.dumps({
        "endpoint": ENDPOINT,
        "http_status": status,
        "request_count": 1,
        "graphql_errors": document.get("errors"),
        "multi_city_contract_exposed": exposed,
        "candidate_queries": candidate_queries,
        "candidate_inputs": candidate_inputs,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
