from __future__ import annotations

import asyncio
from importlib.metadata import version
import json

from cheap_flight_radar.providers.gflights import GFlightsAdapter, PRODUCTION_USER_AGENT


async def main() -> None:
    adapter = GFlightsAdapter()
    probes = []

    async def run(name, call):
        try:
            result = await call()
            first = result.records[0] if result.records else None
            probes.append(
                {
                    "surface": name,
                    "coverage_state": result.coverage_state,
                    "records": len(result.records),
                    "first_price_twd": first.current_price_twd if first else None,
                    "first_verification_state": first.verification_state if first else None,
                    "error": result.error,
                }
            )
        except Exception as exc:
            probes.append(
                {
                    "surface": name,
                    "coverage_state": "exception",
                    "records": 0,
                    "first_price_twd": None,
                    "first_verification_state": None,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

    await run(
        "flight_deals",
        lambda: adapter.flight_deals(origin="TPE", anchor_departure="2026-10-05", anchor_return="2026-10-09"),
    )
    await run("explore", lambda: adapter.explore(origin="TPE"))
    await run(
        "exact_offer",
        lambda: adapter.exact(
            origin="TPE",
            destination="NRT",
            departure_date="2026-10-05",
            return_date="2026-10-09",
            resolve_booking_offer=True,
        ),
    )
    await run(
        "cheapest_dates",
        lambda: adapter.cheapest_dates(
            origin="TPE",
            destination="NRT",
            start_date="2026-10-01",
            months=1,
            trip_duration_days=4,
        ),
    )
    await run(
        "open_jaw",
        lambda: adapter.open_jaw(
            legs=(
                ("TPE", "NRT", "2026-10-05"),
                ("KIX", "KHH", "2026-10-09"),
            )
        ),
    )

    payload = {
        "gflights_version": version("gflights"),
        "user_agent": PRODUCTION_USER_AGENT,
        "proxy_policy": "explicit_none_in_GFlightsAdapter",
        "retry_policy": "none",
        "identity_rotation": "forbidden_not_used",
        "probe_count": len(probes),
        "probes": probes,
    }
    print("SR_B_RESULT=" + json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
