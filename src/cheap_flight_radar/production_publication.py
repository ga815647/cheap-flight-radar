"""Backward-compatible anomaly-first Radar publication.

Schema v1 manifests keep their historical transition rendering unchanged.
Schema v2 manifests render Deals and Signals as the primary user-facing model;
legacy price/time views do not decide or reorder v2 Deals.
"""
from __future__ import annotations

import argparse
from datetime import datetime
from html import escape
import json
from pathlib import Path
import shutil
from typing import Any, Mapping, Sequence

from . import publication as legacy
from .price_history import FareHistorySnapshot, FareObservation, compare_with_history, snapshot_from_json

MANIFEST_SCHEMA_VERSION = 2


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("publication timestamps must be timezone-aware")
    return parsed


def _load_raw_manifest(path: Path) -> Mapping[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise TypeError("publication manifest must be a mapping")
    schema = raw.get("schema_version")
    if schema not in (1, MANIFEST_SCHEMA_VERSION):
        raise ValueError(f"unsupported publication manifest schema_version: {schema!r}")
    for key in ("radar_run_id", "run_at", "history_snapshot_path"):
        if key not in raw:
            raise ValueError(f"publication manifest missing {key!r}")
    _parse_datetime(str(raw["run_at"]))
    legacy.safe_run_id(str(raw["radar_run_id"]))
    if schema == 2:
        for key in ("deals", "signals", "coverage"):
            if key not in raw:
                raise ValueError(f"schema v2 publication manifest missing {key!r}")
    return raw


def _snapshot_for_manifest(manifest: Mapping[str, Any], history_dir: Path) -> FareHistorySnapshot:
    relative = Path(str(manifest["history_snapshot_path"]))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("history_snapshot_path must stay inside history_dir")
    snapshot = snapshot_from_json((history_dir / relative).read_text(encoding="utf-8"))
    if snapshot.radar_run_id != str(manifest["radar_run_id"]):
        raise ValueError("manifest radar_run_id does not match history snapshot")
    if _parse_datetime(snapshot.run_at) != _parse_datetime(str(manifest["run_at"])):
        raise ValueError("manifest run_at does not match history snapshot")
    return snapshot


def _money(value: Any) -> str:
    if value is None:
        return "unknown"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "unknown"
    return f"TWD {int(round(number)):,}"


def _percent(value: Any) -> str:
    if value is None:
        return "unknown"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "unknown"
    return f"{number:.1f}% below baseline"


def _record(item: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = item.get(key)
    return value if isinstance(value, Mapping) else {}


def _airport(record: Mapping[str, Any], side: str) -> str:
    identity = record.get(side)
    if isinstance(identity, Mapping) and identity.get("iata"):
        return str(identity["iata"])
    return "???"


def _destination_text(discovery: Mapping[str, Any]) -> str:
    identity = discovery.get("destination")
    if not isinstance(identity, Mapping):
        return _airport(discovery, "destination")
    airport = str(identity.get("iata") or "???")
    city = str(identity.get("city") or "").strip()
    country = str(identity.get("country") or "").strip()
    extras = " · ".join(value for value in (city, country) if value)
    return f"{airport} · {extras}" if extras else airport


def _dates(discovery: Mapping[str, Any]) -> str:
    legs = discovery.get("legs")
    if not isinstance(legs, Sequence) or isinstance(legs, (str, bytes)) or not legs:
        return "dates unknown"
    dates = [str(leg.get("date")) for leg in legs if isinstance(leg, Mapping) and leg.get("date")]
    return " → ".join(dates) if dates else "dates unknown"


def _airlines(exact: Mapping[str, Any], discovery: Mapping[str, Any]) -> str:
    value = exact.get("airlines") or discovery.get("airlines") or []
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return ", ".join(str(item) for item in value if item) or "airline unknown"
    return str(value) if value else "airline unknown"


def _history_html(observation_id: str | None, by_id: Mapping[str, FareObservation], all_history: Sequence[FareObservation], policy: Mapping[str, Any]) -> str:
    if not observation_id or observation_id not in by_id:
        return '<p class="sparse-note">Historical evidence unavailable for this record.</p>'
    comparison = compare_with_history(by_id[observation_id], all_history, policy["price_history"])
    return legacy._history_metrics_html(comparison)


def _deal_card(item: Mapping[str, Any], *, by_id: Mapping[str, FareObservation], all_history: Sequence[FareObservation], policy: Mapping[str, Any]) -> str:
    discovery = _record(item, "discovery")
    exact = _record(item, "exact")
    origin = _airport(discovery, "origin")
    destination = _destination_text(discovery)
    current = item.get("current_complete_airfare_twd") or exact.get("current_price_twd")
    anomaly_scope = str(item.get("anomaly_scope") or "")
    if item.get("anomaly_baseline_twd") is not None:
        typical = item.get("anomaly_baseline_twd")
        baseline_label = "Destination baseline" if anomaly_scope == "destination_airport_all_taiwan_origins" else "Selected baseline"
    else:
        typical = discovery.get("typical_price_twd")
        baseline_label = "Provider typical (legacy)"
    anomaly = item.get("anomaly_strength_percent")
    source = str(item.get("anomaly_source") or "unknown")
    booking = exact.get("booking_url") or discovery.get("booking_url") or exact.get("evidence_url") or discovery.get("evidence_url")
    link = (
        f'<p class="source"><a href="{escape(str(booking), quote=True)}" rel="noreferrer">Booking / evidence</a></p>'
        if booking else '<p class="source">Reproducible search parameters preserved in run evidence.</p>'
    )
    return (
        '<article class="view-card">'
        '<div class="view-label">Deal</div>'
        f'<h3 class="route">{escape(origin)} → {escape(destination)}</h3>'
        f'<p class="price">{escape(_money(current))}</p>'
        f'<p class="trip-meta">{escape(_dates(discovery))} · exact revalidated · {escape(_airlines(exact, discovery))}</p>'
        '<div class="metric-row">'
        f'<span class="metric good"><small>Anomaly</small><strong>{escape(_percent(anomaly))}</strong></span>'
        f'<span class="metric"><small>{escape(baseline_label)}</small><strong>{escape(_money(typical))}</strong></span>'
        f'<span class="metric"><small>Authority</small><strong>{escape(source)}</strong></span>'
        '</div>'
        + _history_html(str(item.get("observation_id")) if item.get("observation_id") else None, by_id, all_history, policy)
        + link
        + '</article>'
    )


def _signal_card(item: Mapping[str, Any]) -> str:
    discovery = _record(item, "discovery")
    exact = _record(item, "exact")
    origin = _airport(discovery, "origin")
    destination = _destination_text(discovery)
    price = item.get("current_complete_airfare_twd") or exact.get("current_price_twd") or discovery.get("current_price_twd")
    state = str(item.get("state") or "signal")
    reason = str(item.get("reason") or "weak evidence")
    return (
        '<article class="candidate">'
        f'<h3 class="route">{escape(origin)} → {escape(destination)}</h3>'
        f'<p class="price">{escape(_money(price))}</p>'
        f'<p class="trip-meta">{escape(_dates(discovery))} · {escape(state)}</p>'
        f'<p class="sparse-note">{escape(reason)}</p>'
        '</article>'
    )


def _coverage_html(manifest: Mapping[str, Any]) -> str:
    coverage = manifest.get("coverage")
    if not isinstance(coverage, Mapping):
        return ""
    origins = coverage.get("origins") if isinstance(coverage.get("origins"), Mapping) else {}
    markets = coverage.get("markets") if isinstance(coverage.get("markets"), Mapping) else {}
    origin_rows = []
    for origin, details in origins.items():
        details = details if isinstance(details, Mapping) else {}
        status = str(details.get("status", "unknown"))
        returned = details.get("returned_flight_deals", 0)
        qualified = details.get("qualified_deals", 0)
        origin_rows.append(
            f'<li><span>{escape(str(origin))} · {escape(str(returned))} returned / {escape(str(qualified))} qualified</span>{legacy._status_badge(status)}</li>'
        )
    market_rows = []
    for market, details in markets.items():
        details = details if isinstance(details, Mapping) else {}
        market_rows.append(
            '<li><span>' + escape(str(market)) + '</span><span class="status-badge neutral">'
            + escape(f"{details.get('discovered', 0)} discovered · {details.get('deals', 0)} Deals") + '</span></li>'
        )
    failures = manifest.get("provider_failures")
    failure_rows = []
    if isinstance(failures, Sequence) and not isinstance(failures, (str, bytes)):
        for failure in failures:
            if isinstance(failure, Mapping):
                failure_rows.append(
                    f'<li>{escape(str(failure.get("origin", "?")))} · {escape(str(failure.get("surface", "provider")))} — {escape(str(failure.get("error", "failed")))}</li>'
                )
    failures_html = (
        '<section class="details-card"><details><summary>Provider failures</summary><ul class="diagnostic-list">'
        + "".join(failure_rows) + '</ul></details></section>'
        if failure_rows else ""
    )
    return (
        '<section class="ops-card"><div class="section-heading"><div><h2>Coverage &amp; evidence</h2>'
        '<p>Origin attempts and shared Asia/Oceania pipeline coverage for this immutable run.</p></div></div>'
        '<div class="ops-grid">'
        '<div class="ops-block"><h3>Origin sweeps</h3><ul class="ops-list">' + "".join(origin_rows) + '</ul></div>'
        '<div class="ops-block"><h3>Market slices</h3><ul class="ops-list">' + "".join(market_rows) + '</ul></div>'
        '<div class="ops-block"><h3>Semantics</h3><ul class="ops-list">'
        '<li><span>Flight Deals</span><span class="status-badge good">destination-airport truth</span></li>'
        '<li><span>Google exact</span><span class="status-badge good">revalidation</span></li>'
        '<li><span>Fixed watch</span><span class="status-badge neutral">Signal only</span></li>'
        '</ul></div></div></section>' + failures_html
    )


def render_v2_run_page(manifest: Mapping[str, Any], snapshot: FareHistorySnapshot, all_history: Sequence[FareObservation], policy: Mapping[str, Any]) -> str:
    by_id = {item.observation_id: item for item in snapshot.observations}
    deals = manifest.get("deals") if isinstance(manifest.get("deals"), Sequence) else []
    signals = manifest.get("signals") if isinstance(manifest.get("signals"), Sequence) else []
    deal_cards = "".join(
        _deal_card(item, by_id=by_id, all_history=all_history, policy=policy)
        for item in deals if isinstance(item, Mapping)
    ) or '<p class="empty">No qualified current Deal survived exact revalidation in this run.</p>'
    signal_cards = "".join(_signal_card(item) for item in signals if isinstance(item, Mapping)) or '<p class="empty">No weaker Signals recorded in this run.</p>'
    history_path = escape(str(manifest["history_snapshot_path"]))
    return (
        '<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light">'
        f'<title>Cheap Flight Radar — {escape(snapshot.radar_run_id)}</title><style>{legacy.SITE_CSS}</style></head>'
        '<body><main class="shell">'
        '<div class="topbar"><a class="brand" href="../../"><span class="brand-mark" aria-hidden="true">↗</span><span>Cheap Flight Radar</span></a>'
        '<nav class="nav"><a href="../../latest/">Latest</a><a href="../../">All runs</a></nav></div>'
        '<header class="hero"><p class="eyebrow">Taiwan → Asia / Oceania · anomaly-first</p>'
        '<h1>Qualified cheap airfare Deals</h1>'
        '<p class="hero-copy">Deals are ranked by destination-airport anomaly strength across accepted Taiwan origins, then current complete airfare. Signals remain separate and cannot outrank a Deal.</p>'
        '<div class="run-meta">'
        f'<span class="chip">Run at {escape(snapshot.run_at)}</span><span class="chip">TPE · TSA · RMQ · KHH</span>'
        '<span class="chip">Google Flight Deals → exact revalidation</span></div></header>'
        '<div class="section-heading"><div><h2>Deals</h2><p>Qualified external anomaly truth + current exact complete airfare.</p></div></div>'
        '<section class="hero-grid" aria-label="Qualified Deals">' + deal_cards + '</section>'
        '<div class="section-heading"><div><h2>Signals</h2><p>Weak seeds, stale anomalies, and exact candidates without qualified anomaly truth.</p></div></div>'
        '<section class="market-section"><div class="candidate-list">' + signal_cards + '</div></section>'
        + _coverage_html(manifest)
        + '<section class="details-card"><details><summary>Transition / diagnostic views</summary>'
        '<p class="empty">Absolute Cheapest, Near-Term Cheapest, and other legacy views are diagnostic only for schema-v2 runs and do not determine Deal status or order.</p></details></section>'
        + '<p class="provenance">Destination-airport anomaly baselines pool TPE/TSA/RMQ/KHH while each ticket retains its actual origin. Own price history is supplemental/fallback evidence; sparse history cannot block a Deal already qualified by a higher-priority external authority.<br>'
        'Immutable evidence snapshot: <code>' + history_path + '</code></p>'
        '</main></body></html>\n'
    )


def build_site(*, policy_path: Path, history_dir: Path, manifest_dir: Path, site_dir: Path) -> tuple[Path, ...]:
    policy = legacy.load_policy(policy_path)
    snapshots = legacy.load_history_snapshots(history_dir)
    all_history = tuple(observation for snapshot in snapshots for observation in snapshot.observations)
    manifests = [_load_raw_manifest(path) for path in sorted(manifest_dir.glob("*.json"))]
    manifests.sort(key=lambda item: (_parse_datetime(str(item["run_at"])), str(item["radar_run_id"])))
    if site_dir.exists():
        shutil.rmtree(site_dir)
    site_dir.mkdir(parents=True)
    (site_dir / ".nojekyll").write_text("", encoding="utf-8")
    entries: list[tuple[Mapping[str, Any], str]] = []
    outputs: list[Path] = []
    for manifest in manifests:
        snapshot = _snapshot_for_manifest(manifest, history_dir)
        slug = legacy.safe_run_id(snapshot.radar_run_id)
        run_dir = site_dir / "runs" / slug
        run_dir.mkdir(parents=True, exist_ok=True)
        page = run_dir / "index.html"
        html = legacy.render_run_page(manifest, snapshot, all_history, policy) if manifest["schema_version"] == 1 else render_v2_run_page(manifest, snapshot, all_history, policy)
        page.write_text(html, encoding="utf-8")
        outputs.append(page)
        entries.append((manifest, slug))
    index = site_dir / "index.html"
    index.write_text(legacy._render_index(entries), encoding="utf-8")
    outputs.append(index)
    latest_dir = site_dir / "latest"
    latest_dir.mkdir(parents=True, exist_ok=True)
    latest = latest_dir / "index.html"
    if entries:
        latest.write_bytes((site_dir / "runs" / entries[-1][1] / "index.html").read_bytes())
    else:
        latest.write_text("<!doctype html><html><body><p>No Radar runs published.</p></body></html>\n", encoding="utf-8")
    outputs.append(latest)
    return tuple(outputs)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build backward-compatible anomaly-first Cheap Flight Radar publication")
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--history-dir", type=Path, required=True)
    parser.add_argument("--manifest-dir", type=Path, required=True)
    parser.add_argument("--site-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    build_site(policy_path=args.policy, history_dir=args.history_dir, manifest_dir=args.manifest_dir, site_dir=args.site_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
