#!/usr/bin/env python3
"""One-shot public 12306 probe for Fujian rail convergence research.

This is deliberately narrow: no login, no CAPTCHA handling, no retries that try to
circumvent rate limits, and no browser fingerprinting/proxy behavior. It only calls
public 12306 ticket/price surfaces and emits compact JSON evidence to stdout.
"""

from __future__ import annotations

import argparse
import json
import sys
from urllib.parse import urlencode
from urllib.request import Request, build_opener

BASE = "https://kyfw.12306.cn"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) CheapFlightRadar/0.1 public-evidence-probe"


def fetch_json(opener, path: str, params: dict[str, str]) -> tuple[int, str, object | None]:
    url = f"{BASE}{path}?{urlencode(params)}"
    req = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json,text/plain,*/*",
            "Referer": f"{BASE}/otn/leftTicket/init",
        },
    )
    try:
        with opener.open(req, timeout=20) as response:
            raw = response.read().decode("utf-8", errors="replace")
            status = response.status
    except Exception as exc:  # research probe: preserve exact failure class/message
        return 0, f"{type(exc).__name__}: {exc}", None

    try:
        return status, raw[:1000], json.loads(raw)
    except json.JSONDecodeError:
        return status, raw[:1000], None


def train_summary(result: str, station_map: dict[str, str]) -> dict[str, object]:
    fields = result.split("|")
    def field(index: int) -> str | None:
        return fields[index] if index < len(fields) and fields[index] else None

    return {
        "train_no": field(2),
        "train_code": field(3),
        "from": station_map.get(field(6) or "", field(6)),
        "to": station_map.get(field(7) or "", field(7)),
        "depart": field(8),
        "arrive": field(9),
        "duration": field(10),
        "can_web_buy": field(11),
        "train_date": field(13),
        "from_station_no": field(16),
        "to_station_no": field(17),
        "second_class_availability": field(30),
        "first_class_availability": field(31),
        "business_availability": field(32),
        "seat_types": field(35),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--from-code", default="XKS")
    parser.add_argument("--to-code", default="FYS")
    args = parser.parse_args()

    opener = build_opener()
    left_params = {
        "leftTicketDTO.train_date": args.date,
        "leftTicketDTO.from_station": args.from_code,
        "leftTicketDTO.to_station": args.to_code,
        "purpose_codes": "ADULT",
    }
    status, preview, payload = fetch_json(opener, "/otn/leftTicket/query", left_params)
    evidence: dict[str, object] = {
        "request": {"date": args.date, "from_code": args.from_code, "to_code": args.to_code},
        "left_ticket": {"status": status, "preview": preview},
    }

    if not isinstance(payload, dict):
        print(json.dumps(evidence, ensure_ascii=False, indent=2))
        return 2

    data = payload.get("data")
    if not isinstance(data, dict):
        evidence["left_ticket"] = {"status": status, "payload": payload}
        print(json.dumps(evidence, ensure_ascii=False, indent=2))
        return 3

    station_map = data.get("map") if isinstance(data.get("map"), dict) else {}
    raw_results = data.get("result") if isinstance(data.get("result"), list) else []
    summaries = [train_summary(item, station_map) for item in raw_results]
    evidence["left_ticket"] = {
        "status": status,
        "http_status": payload.get("httpstatus"),
        "count": len(summaries),
        "trains": summaries[:12],
    }

    selected = next(
        (
            s for s in summaries
            if isinstance(s.get("train_code"), str)
            and str(s["train_code"]).startswith(("G", "D", "C"))
            and s.get("can_web_buy") == "Y"
        ),
        None,
    )
    if selected:
        price_params = {
            "train_no": str(selected.get("train_no") or ""),
            "from_station_no": str(selected.get("from_station_no") or ""),
            "to_station_no": str(selected.get("to_station_no") or ""),
            "seat_types": str(selected.get("seat_types") or ""),
            "train_date": args.date,
        }
        pstatus, ppreview, ppayload = fetch_json(
            opener, "/otn/leftTicket/queryTicketPrice", price_params
        )
        evidence["selected_train_price"] = {
            "train": selected,
            "status": pstatus,
            "preview": ppreview,
            "payload": ppayload,
        }

    public_price_params = {
        "leftTicketDTO.train_date": args.date,
        "leftTicketDTO.from_station": args.from_code,
        "leftTicketDTO.to_station": args.to_code,
        "purpose_codes": "00",
    }
    pstatus, ppreview, ppayload = fetch_json(
        opener, "/otn/leftTicketPrice/query", public_price_params
    )
    evidence["public_price_query"] = {
        "status": pstatus,
        "preview": ppreview,
        "payload_type": type(ppayload).__name__ if ppayload is not None else None,
        "payload": ppayload,
    }

    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
