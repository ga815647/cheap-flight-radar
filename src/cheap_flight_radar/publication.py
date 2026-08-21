"""Deterministic GitHub Pages publication for Cheap Flight Radar."""

from __future__ import annotations

import argparse
from datetime import datetime
from html import escape
import json
from pathlib import Path
import re
import shutil
from typing import Any, Mapping, Sequence

import yaml

from .price_history import (
    FareHistoryComparison,
    FareHistorySnapshot,
    FareObservation,
    compare_with_history,
    current_live_floors,
    snapshot_from_json,
)

MANIFEST_SCHEMA_VERSION = 1

SITE_CSS = """
:root{
  color-scheme:light;
  font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  color:#172033;background:#f4f7fb;
  --ink:#172033;--muted:#667085;--line:#e4e9f1;--card:#fff;
  --brand:#155eef;--brand-soft:#eef4ff;--good:#067647;--good-soft:#ecfdf3;
  --warn:#b54708;--warn-soft:#fffaeb;--bad:#b42318;--bad-soft:#fef3f2;
  --neutral:#475467;--neutral-soft:#f2f4f7;--shadow:0 12px 30px rgba(16,24,40,.06)
}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:#f4f7fb;color:var(--ink)}
a{color:inherit}.shell{width:min(1180px,calc(100% - 32px));margin:0 auto;padding:28px 0 56px}
.topbar{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:18px}
.brand{display:flex;align-items:center;gap:10px;font-weight:800;letter-spacing:-.02em;text-decoration:none}
.brand-mark{width:34px;height:34px;border-radius:11px;background:linear-gradient(135deg,#155eef,#53b1fd);display:grid;place-items:center;color:#fff;box-shadow:var(--shadow)}
.nav{display:flex;gap:8px;flex-wrap:wrap}.nav a{font-size:.9rem;text-decoration:none;padding:8px 11px;border:1px solid var(--line);border-radius:999px;background:#fff;color:#344054}
.hero{position:relative;overflow:hidden;border:1px solid #dbe6ff;border-radius:24px;padding:26px;background:linear-gradient(135deg,#fff 0%,#f7faff 55%,#edf4ff 100%);box-shadow:var(--shadow);margin-bottom:18px}
.hero:after{content:"";position:absolute;width:280px;height:280px;border-radius:50%;right:-110px;top:-140px;background:rgba(21,94,239,.08)}
.eyebrow{font-size:.76rem;text-transform:uppercase;letter-spacing:.11em;font-weight:800;color:var(--brand);margin:0 0 8px}.hero h1{font-size:clamp(1.7rem,3vw,2.55rem);line-height:1.05;letter-spacing:-.04em;margin:0 0 10px;max-width:860px}
.hero-copy{color:#475467;margin:0;max-width:820px;line-height:1.55}.run-meta{display:flex;gap:8px;flex-wrap:wrap;margin-top:17px}.chip,.status-badge{display:inline-flex;align-items:center;gap:6px;border-radius:999px;padding:6px 9px;font-size:.78rem;font-weight:700;line-height:1.15}
.chip{background:#fff;border:1px solid var(--line);color:#475467}.status-badge.good{background:var(--good-soft);color:var(--good)}.status-badge.warn{background:var(--warn-soft);color:var(--warn)}.status-badge.bad{background:var(--bad-soft);color:var(--bad)}.status-badge.neutral{background:var(--neutral-soft);color:var(--neutral)}
.coverage-strip{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:0 0 22px}.coverage-pill{background:#fff;border:1px solid var(--line);border-radius:16px;padding:12px 14px;display:flex;align-items:center;justify-content:space-between;gap:12px;box-shadow:0 4px 14px rgba(16,24,40,.03)}.coverage-pill span:first-child{font-size:.78rem;color:var(--muted);font-weight:700;text-transform:uppercase;letter-spacing:.06em}
.section-heading{display:flex;justify-content:space-between;align-items:end;gap:16px;margin:30px 0 12px}.section-heading h2{font-size:1.15rem;margin:0;letter-spacing:-.02em}.section-heading p{font-size:.86rem;color:var(--muted);margin:0}
.hero-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.view-card,.market-section,.ops-card,.details-card{background:var(--card);border:1px solid var(--line);border-radius:20px;box-shadow:0 7px 20px rgba(16,24,40,.035)}
.view-card{padding:19px;min-height:285px;display:flex;flex-direction:column}.view-label{font-size:.73rem;text-transform:uppercase;letter-spacing:.08em;font-weight:800;color:var(--brand);margin-bottom:10px}.route{font-size:1.15rem;font-weight:800;line-height:1.25;letter-spacing:-.02em;margin:0 0 6px}.price{font-size:clamp(2rem,4vw,2.8rem);font-weight:850;letter-spacing:-.045em;margin:6px 0 7px}.trip-meta{color:#475467;font-size:.9rem;margin:0 0 13px;line-height:1.45}.source{color:#7b8494;font-size:.78rem;margin:9px 0 0;word-break:break-word}.card-footer{margin-top:auto}
.metric-row{display:flex;flex-wrap:wrap;gap:7px;margin:8px 0}.metric{display:inline-flex;flex-direction:column;gap:1px;padding:7px 9px;border-radius:11px;background:#f8fafc;border:1px solid #edf1f6;min-width:92px}.metric small{font-size:.66rem;text-transform:uppercase;letter-spacing:.05em;color:#7b8494;font-weight:700}.metric strong{font-size:.82rem;color:#344054}.metric.good strong{color:var(--good)}.metric.warn strong{color:var(--warn)}
.delta{display:inline-flex;align-items:center;gap:5px;font-size:.83rem;font-weight:800;padding:7px 9px;border-radius:10px}.delta.good{background:var(--good-soft);color:var(--good)}.delta.warn{background:var(--warn-soft);color:var(--warn)}.delta.neutral{background:var(--neutral-soft);color:var(--neutral)}
.sparse-note{font-size:.78rem;color:#667085;background:#f8fafc;border-left:3px solid #98a2b3;padding:8px 10px;border-radius:8px;margin:9px 0 0}.percentile{margin-top:9px}.percentile-line{display:flex;justify-content:space-between;font-size:.76rem;color:#667085;margin-bottom:5px}.percentile-track{height:6px;background:#eef2f6;border-radius:999px;overflow:hidden}.percentile-fill{height:100%;background:linear-gradient(90deg,#12b76a,#53b1fd);border-radius:inherit}
.market-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.market-section{padding:18px}.market-section h2{font-size:1rem;margin:0 0 4px}.market-kicker{font-size:.75rem;color:var(--muted);margin:0 0 12px}.candidate-list{display:grid;gap:9px}.candidate{border:1px solid #edf0f4;background:#fbfcfe;border-radius:14px;padding:13px}.candidate .route{font-size:.98rem}.candidate .price{font-size:1.45rem;margin:3px 0 4px}.candidate .trip-meta{font-size:.81rem;margin-bottom:8px}.candidate .metric{min-width:auto;padding:5px 7px}.candidate .metric small{display:none}.candidate .metric strong{font-size:.74rem}
.empty{color:#667085;font-size:.88rem;line-height:1.5;background:#f8fafc;border:1px dashed #d0d5dd;border-radius:13px;padding:14px;margin:8px 0 0}.ops-card{padding:19px;margin-top:14px}.ops-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.ops-block{border:1px solid #edf0f4;border-radius:14px;padding:13px}.ops-block h3{font-size:.83rem;margin:0 0 9px;color:#344054}.ops-list{list-style:none;margin:0;padding:0;display:grid;gap:7px}.ops-list li{font-size:.78rem;color:#475467;display:flex;justify-content:space-between;gap:9px}.ops-list code{font-size:.72rem}
details{border-top:1px solid #edf0f4;margin-top:12px;padding-top:10px}summary{cursor:pointer;color:#475467;font-size:.8rem;font-weight:750;list-style-position:outside}.history-detail ul,.diagnostic-list{margin:9px 0 0;padding-left:19px;color:#667085;font-size:.78rem;line-height:1.55}.details-card{padding:17px 19px;margin-top:14px}.details-card summary{font-size:.9rem;color:#344054}.details-card details{border-top:0;padding-top:0;margin-top:0}.details-card .diagnostic-list{font-size:.84rem}
.provenance{margin-top:18px;font-size:.76rem;color:#7b8494;line-height:1.55}.provenance code{word-break:break-all}.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
.index-hero{display:grid;grid-template-columns:1.4fr .6fr;gap:14px}.latest-card,.archive-card{background:#fff;border:1px solid var(--line);border-radius:20px;padding:20px;box-shadow:var(--shadow)}.latest-card h2,.archive-card h2{margin:0 0 8px;font-size:1.05rem}.latest-link{display:inline-flex;margin-top:13px;text-decoration:none;background:var(--brand);color:#fff;font-weight:800;border-radius:12px;padding:10px 13px}.run-list{list-style:none;padding:0;margin:12px 0 0;display:grid;gap:8px}.run-list a{display:flex;justify-content:space-between;gap:12px;text-decoration:none;padding:11px 12px;border:1px solid #edf0f4;border-radius:12px;background:#fbfcfe}.run-list strong{font-size:.84rem}.run-list time{font-size:.74rem;color:#667085;white-space:nowrap}
@media(max-width:780px){.shell{width:min(100% - 22px,1180px);padding-top:18px}.topbar{align-items:flex-start}.hero{padding:20px;border-radius:20px}.coverage-strip,.ops-grid,.index-hero{grid-template-columns:1fr}.hero-grid,.market-grid{grid-template-columns:1fr}.section-heading{align-items:flex-start;flex-direction:column;gap:3px}.view-card{min-height:0}.run-list a{flex-direction:column}.run-list time{white-space:normal}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
""".strip()


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("publication timestamps must be timezone-aware")
    return parsed


def safe_run_id(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-.")
    if not safe:
        raise ValueError("radar_run_id does not contain a path-safe character")
    return safe


def load_policy(path: Path) -> Mapping[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise TypeError("flight-radar policy must be a mapping")
    return raw


def load_manifest(path: Path) -> Mapping[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise TypeError("publication manifest must be a mapping")
    if raw.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise ValueError("unsupported publication manifest schema_version")
    required = ("radar_run_id", "run_at", "history_snapshot_path", "sections", "markets", "coverage")
    for key in required:
        if key not in raw:
            raise ValueError(f"publication manifest missing {key!r}")
    _parse_datetime(str(raw["run_at"]))
    safe_run_id(str(raw["radar_run_id"]))
    return raw


def load_history_snapshots(history_dir: Path) -> tuple[FareHistorySnapshot, ...]:
    root = history_dir / "data" / "price-history"
    if not root.exists():
        return ()
    snapshots = [snapshot_from_json(path.read_text(encoding="utf-8")) for path in sorted(root.rglob("*.json"))]
    return tuple(sorted(snapshots, key=lambda item: (_parse_datetime(item.run_at), item.radar_run_id)))


def _history_observations(snapshots: Sequence[FareHistorySnapshot]) -> tuple[FareObservation, ...]:
    return tuple(observation for snapshot in snapshots for observation in snapshot.observations)


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


def _money(value: float | int | None) -> str:
    if value is None:
        return "unknown"
    number = float(value)
    if number.is_integer():
        return f"TWD {int(number):,}"
    return f"TWD {number:,.2f}"


def _percent(value: float | None) -> str:
    if value is None:
        return "unknown"
    return f"{value:+.1f}%"


def _airport_label(iata: str, policy: Mapping[str, Any]) -> str:
    labels = policy["search"]["display_policy"]["taiwan_airport_labels"]
    label = labels.get(iata) if isinstance(labels, Mapping) else None
    return f"{label}（{iata}）" if label else iata


def _candidate_details(manifest: Mapping[str, Any], observation_id: str) -> Mapping[str, Any]:
    details = manifest.get("candidate_details", {})
    if not isinstance(details, Mapping):
        raise TypeError("candidate_details must be a mapping")
    item = details.get(observation_id, {})
    if not isinstance(item, Mapping):
        raise TypeError("candidate detail must be a mapping")
    return item


def _status_tone(value: str) -> str:
    normalized = value.lower()
    if normalized in {"complete", "attempted", "revalidated", "available", "high", "medium"}:
        return "good"
    if normalized in {"partial", "sparse", "low"} or "due" in normalized or "non_converged" in normalized:
        return "warn"
    if normalized in {"incomplete", "failed", "error"}:
        return "bad"
    return "neutral"


def _status_badge(value: str, *, label: str | None = None) -> str:
    tone = _status_tone(value)
    text = f"{label}: {value}" if label else value
    return f'<span class="status-badge {tone}">{escape(text)}</span>'


def _history_lines(comparison: FareHistoryComparison) -> list[str]:
    lines = [f"Comparable samples: {comparison.sample_count} · confidence: {comparison.confidence}"]
    if comparison.all_time_low_twd is None:
        lines.append("Historical/rolling low: no prior comparable observation")
    else:
        lines.append(f"Prior all-time comparable low: {_money(comparison.all_time_low_twd)}")
        for days in sorted(comparison.rolling_lows_twd):
            statistic = comparison.rolling_lows_twd[days]
            if statistic.value is not None:
                lines.append(f"{days}-day rolling low: {_money(statistic.value)} ({statistic.sample_count} samples)")
    if comparison.selected_baseline_twd is None:
        lines.append("Recent baseline: insufficient comparable history")
    else:
        lines.append(f"Recent baseline: {_money(comparison.selected_baseline_twd)} ({comparison.selected_baseline_window_days}-day median)")
        lines.append(f"Percent below recent baseline: {_percent(comparison.percent_below_baseline)}")
    if comparison.historical_percentile is not None:
        lines.append(f"Historical percentile: {comparison.historical_percentile:.1f}th")
    if comparison.confidence in {"none", "sparse", "low"}:
        lines.append("Sparse-history note: evidence density is limited; do not infer a precise market percentile.")
    if comparison.anomaly_label:
        lines.append(f"Historical label: {comparison.anomaly_label}")
    return lines


def _history_metrics_html(comparison: FareHistoryComparison) -> str:
    metrics = [
        '<div class="metric"><small>Samples</small><strong>' + str(comparison.sample_count) + '</strong></div>',
        '<div class="metric"><small>Confidence</small><strong>' + escape(comparison.confidence.title()) + '</strong></div>',
    ]
    if comparison.all_time_low_twd is not None:
        metrics.append('<div class="metric"><small>Prior low</small><strong>' + escape(_money(comparison.all_time_low_twd)) + '</strong></div>')
    for days in sorted(comparison.rolling_lows_twd):
        statistic = comparison.rolling_lows_twd[days]
        if statistic.value is not None and days in {30, 90, 365}:
            metrics.append('<div class="metric"><small>' + str(days) + 'd low</small><strong>' + escape(_money(statistic.value)) + '</strong></div>')
    baseline = ""
    if comparison.selected_baseline_twd is not None:
        delta = comparison.percent_below_baseline
        if delta is None:
            delta_html = '<span class="delta neutral">Baseline available</span>'
        elif delta > 0:
            delta_html = f'<span class="delta good">↓ {abs(delta):.1f}% vs baseline</span>'
        elif delta < 0:
            delta_html = f'<span class="delta warn">↑ {abs(delta):.1f}% vs baseline</span>'
        else:
            delta_html = '<span class="delta neutral">At recent baseline</span>'
        baseline = (
            '<div class="metric-row">' + delta_html +
            '<div class="metric"><small>Baseline</small><strong>' + escape(_money(comparison.selected_baseline_twd)) +
            f' · {comparison.selected_baseline_window_days}d median</strong></div></div>'
        )
    percentile = ""
    if comparison.historical_percentile is not None:
        width = max(0.0, min(100.0, comparison.historical_percentile))
        percentile = (
            '<div class="percentile"><div class="percentile-line"><span>Historical percentile</span>'
            f'<strong>{comparison.historical_percentile:.1f}th</strong></div>'
            f'<div class="percentile-track"><div class="percentile-fill" style="width:{width:.1f}%"></div></div></div>'
        )
    sparse = ""
    if comparison.confidence in {"none", "sparse", "low"}:
        sparse = '<p class="sparse-note">Sparse history — evidence density is limited; do not infer a precise market percentile.</p>'
    anomaly = ""
    if comparison.anomaly_label:
        anomaly = '<div class="metric-row">' + _status_badge(comparison.anomaly_label, label="History") + '</div>'
    detail_rows = "".join(f"<li>{escape(line)}</li>" for line in _history_lines(comparison))
    return (
        '<div class="metric-row">' + "".join(metrics) + '</div>' + baseline + percentile + sparse + anomaly +
        '<details class="history-detail"><summary>Historical evidence details</summary><ul>' + detail_rows + '</ul></details>'
    )


def _candidate_html(
    observation: FareObservation,
    comparison: FareHistoryComparison,
    manifest: Mapping[str, Any],
    policy: Mapping[str, Any],
    *,
    view_label: str | None = None,
    compact: bool = False,
) -> str:
    details = _candidate_details(manifest, observation.observation_id)
    origin = _airport_label(observation.origin, policy)
    return_date = details.get("return_date")
    date_text = observation.departure_date
    if return_date:
        date_text += f" → {return_date}"
    title = details.get("title") or f"{origin} → {observation.destination}"
    tag = "article"
    class_name = "candidate" if compact else "view-card"
    label_html = f'<div class="view-label">{escape(view_label)}</div>' if view_label else ""
    return (
        f'<{tag} class="{class_name}">{label_html}'
        f'<h3 class="route">{escape(str(title))}</h3>'
        f'<p class="price">{escape(_money(observation.normalized_twd_price))}</p>'
        f'<p class="trip-meta">{escape(date_text)} · {escape(observation.trip_type)} · {escape(observation.verification_state)}</p>'
        '<div class="card-footer">'
        + _history_metrics_html(comparison)
        + f'<p class="source">Evidence: {escape(observation.source_id)}</p></div>'
        f'</{tag}>'
    )


def _hero_candidate(
    title: str,
    observation: FareObservation | None,
    comparisons: Mapping[str, FareHistoryComparison],
    manifest: Mapping[str, Any],
    policy: Mapping[str, Any],
    *,
    empty_text: str = "No converged candidate for this view in this run.",
) -> str:
    if observation is None:
        return f'<article class="view-card"><div class="view-label">{escape(title)}</div><p class="empty">{escape(empty_text)}</p></article>'
    return _candidate_html(observation, comparisons[observation.observation_id], manifest, policy, view_label=title)


def _market_section(
    title: str,
    kicker: str,
    ids: Sequence[str],
    by_id: Mapping[str, FareObservation],
    comparisons: Mapping[str, FareHistoryComparison],
    manifest: Mapping[str, Any],
    policy: Mapping[str, Any],
) -> str:
    if not ids:
        body = '<p class="empty">No notable converged candidate in this run.</p>'
    else:
        body = '<div class="candidate-list">' + "".join(
            _candidate_html(by_id[observation_id], comparisons[observation_id], manifest, policy, compact=True)
            for observation_id in ids
        ) + '</div>'
    return f'<section class="market-section"><h2>{escape(title)}</h2><p class="market-kicker">{escape(kicker)}</p>{body}</section>'


def _failed_seeds_html(manifest: Mapping[str, Any]) -> str:
    seeds = manifest.get("failed_seeds", [])
    if not seeds:
        body = '<p class="empty">No failed cheap seeds recorded.</p>'
    else:
        rows = []
        for seed in seeds:
            if not isinstance(seed, Mapping):
                raise TypeError("failed seed must be a mapping")
            route = str(seed.get("route", "unknown route"))
            price = str(seed.get("price", "price unknown"))
            reason = str(seed.get("reason", "did not converge"))
            rows.append(f"<li><strong>{escape(route)}</strong> · {escape(price)} — {escape(reason)}</li>")
        body = '<ul class="diagnostic-list">' + "".join(rows) + '</ul>'
    return '<section class="details-card"><details><summary>Failed / Non-converged Cheap Seeds</summary>' + body + '</details></section>'


def _coverage_data(manifest: Mapping[str, Any]) -> tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]:
    coverage = manifest["coverage"]
    if not isinstance(coverage, Mapping):
        raise TypeError("coverage must be a mapping")
    origins = coverage.get("origins", {})
    fixed = coverage.get("fixed_watch", {})
    china = coverage.get("china", {})
    return (
        origins if isinstance(origins, Mapping) else {},
        fixed if isinstance(fixed, Mapping) else {},
        china if isinstance(china, Mapping) else {},
    )


def _coverage_strip_html(manifest: Mapping[str, Any]) -> str:
    origins, fixed, china = _coverage_data(manifest)
    origin_values = [str(value) for value in origins.values()]
    origin_status = "complete" if origin_values and all(_status_tone(value) == "good" for value in origin_values) else "partial"
    china_status = str(china.get("status", "unknown"))
    pills = [f'<div class="coverage-pill"><span>Origins</span>{_status_badge(origin_status)}</div>']
    # SR-F retired fixed-watch acquisition. Preserve an old immutable run's
    # historical fixed-watch evidence when present, but do not synthesize a
    # current fixed-watch status for new runs.
    if fixed:
        pills.append(
            f'<div class="coverage-pill"><span>Historical fixed watch</span>{_status_badge(str(fixed.get("status", "unknown")))}</div>'
        )
    pills.append(f'<div class="coverage-pill"><span>China mode</span>{_status_badge(china_status)}</div>')
    return '<div class="coverage-strip" aria-label="Radar coverage summary">' + "".join(pills) + '</div>'


def _coverage_html(manifest: Mapping[str, Any], policy: Mapping[str, Any]) -> str:
    origins, fixed, china = _coverage_data(manifest)
    origin_rows = "".join(
        f'<li><span>{escape(str(origin))}</span>{_status_badge(str(state))}</li>'
        for origin, state in sorted(origins.items())
    )
    # Historical immutable manifests may contain fixed-watch evidence from the
    # retired subsystem. Render that evidence from the manifest itself; current
    # SSOT intentionally has no fixed-watch registry/cadence contract.
    source_rows = []
    for item in fixed.get("sources", []):
        source_id = str(item.get("id", "unknown"))
        state = str(item.get("state", "unknown"))
        source_rows.append(f'<li><span>{escape(source_id)}</span>{_status_badge(state)}</li>')
    fixed_block = ""
    if fixed:
        fixed_block = (
            f'<div class="ops-block"><h3>Historical fixed-watch evidence: {escape(str(fixed.get("status", "unknown")))}</h3>'
            '<ul class="ops-list">' + "".join(source_rows) + '</ul></div>'
        )
    china_rows = []
    modes = china.get("modes", {})
    if isinstance(modes, Mapping):
        china_rows = [
            f'<li><span>{escape(str(mode))}</span>{_status_badge(str(state))}</li>'
            for mode, state in sorted(modes.items())
        ]
    return (
        '<section class="ops-card"><div class="section-heading"><div><h2>Coverage &amp; Freshness</h2>'
        '<p>Operational completeness for this immutable run.</p></div></div><div class="ops-grid">'
        '<div class="ops-block"><h3>Origin coverage</h3><ul class="ops-list">' + origin_rows + '</ul></div>'
        + fixed_block
        + f'<div class="ops-block"><h3>China-mode coverage: {escape(str(china.get("status", "unknown")))}</h3><ul class="ops-list">' + "".join(china_rows) + '</ul></div>'
        + '</div></section>'
    )


def _validate_market_ids(markets: Mapping[str, Any], by_id: Mapping[str, FareObservation]) -> None:
    for market_name, ids in markets.items():
        if not isinstance(ids, Sequence) or isinstance(ids, (str, bytes)):
            raise TypeError(f"market {market_name!r} candidates must be a sequence")
        missing = [item for item in ids if item not in by_id]
        if missing:
            raise ValueError(f"market {market_name!r} references unknown observations: {missing}")


def render_run_page(
    manifest: Mapping[str, Any],
    snapshot: FareHistorySnapshot,
    all_history: Sequence[FareObservation],
    policy: Mapping[str, Any],
) -> str:
    by_id = {item.observation_id: item for item in snapshot.observations}
    run_at = _parse_datetime(snapshot.run_at)
    floors = current_live_floors(
        snapshot.observations,
        radar_run_id=snapshot.radar_run_id,
        run_at=run_at,
        horizon_days=int(policy["search"]["horizon_days"]),
        near_term_days=int(policy["search"]["price_time_views"]["near_term"]["departure_within_days"]),
    )
    sections = manifest["sections"]
    markets = manifest["markets"]
    if not isinstance(sections, Mapping) or not isinstance(markets, Mapping):
        raise TypeError("sections and markets must be mappings")
    _validate_market_ids(markets, by_id)

    def selected(name: str) -> FareObservation | None:
        observation_id = sections.get(name)
        if observation_id is None:
            return None
        observation = by_id.get(str(observation_id))
        if observation is None:
            raise ValueError(f"section {name!r} references unknown observation {observation_id!r}")
        return observation

    best_short_break = selected("best_short_break")
    unusual_long_haul = selected("unusual_long_haul_deal")
    displayed_ids = {
        item.observation_id
        for item in (floors.horizon_absolute, floors.near_term, best_short_break, unusual_long_haul)
        if item is not None
    }
    for ids in markets.values():
        displayed_ids.update(str(item) for item in ids)
    comparisons = {
        observation_id: compare_with_history(by_id[observation_id], all_history, policy["price_history"])
        for observation_id in displayed_ids
    }

    hero_cards = (
        _hero_candidate("Absolute Cheapest", floors.horizon_absolute, comparisons, manifest, policy)
        + _hero_candidate("Near-Term Cheapest", floors.near_term, comparisons, manifest, policy)
        + _hero_candidate("Best Short Break", best_short_break, comparisons, manifest, policy)
        + _hero_candidate(
            "Unusual Long-Haul Deal",
            unusual_long_haul,
            comparisons,
            manifest,
            policy,
            empty_text=str(manifest.get("unusual_long_haul_empty_reason", "No converged unusual long-haul deal in this run.")),
        )
    )
    market_cards = (
        _market_section("Japan Notable Candidates", "Specialist Japan radar", list(markets.get("japan", [])), by_id, comparisons, manifest, policy)
        + _market_section("Korea Notable Candidates", "Specialist Korea radar", list(markets.get("korea", [])), by_id, comparisons, manifest, policy)
        + _market_section("China Notable Candidates", "Direct air + gateway modes", list(markets.get("china", [])), by_id, comparisons, manifest, policy)
        + _market_section("World Notable Candidates", "Other international surprises", list(markets.get("world", [])), by_id, comparisons, manifest, policy)
    )
    notes = manifest.get("notes", [])
    notes_html = ""
    if notes:
        notes_html = (
            '<section class="details-card"><details><summary>Run Notes</summary><ul class="diagnostic-list">'
            + "".join(f"<li>{escape(str(note))}</li>" for note in notes)
            + '</ul></details></section>'
        )
    history_path = escape(str(manifest["history_snapshot_path"]))
    run_title = f"Cheap Flight Radar — {snapshot.radar_run_id}"
    return (
        '<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="color-scheme" content="light">'
        f'<title>{escape(run_title)}</title><style>{SITE_CSS}</style></head><body><main class="shell">'
        '<div class="topbar"><a class="brand" href="../../"><span class="brand-mark" aria-hidden="true">↗</span><span>Cheap Flight Radar</span></a>'
        '<nav class="nav" aria-label="Publication navigation"><a href="../../latest/">Latest</a><a href="../../">All runs</a></nav></div>'
        '<header class="hero"><p class="eyebrow">Taiwan → World · 120-day radar</p>'
        f'<h1>Fare radar report</h1><p class="hero-copy">{escape(snapshot.radar_run_id)}</p>'
        '<div class="run-meta">'
        f'<span class="chip">Run at {escape(snapshot.run_at)}</span>'
        '<span class="chip">TPE · TSA · RMQ · KHH</span>'
        '<span class="chip">Immutable historical evidence</span></div></header>'
        + _coverage_strip_html(manifest)
        + '<div class="section-heading"><div><h2>Top signals</h2><p>Price-first views defined by the Radar SSOT.</p></div></div>'
        + '<section class="hero-grid" aria-label="Top Radar views">' + hero_cards + '</section>'
        + '<div class="section-heading"><div><h2>Markets</h2><p>Notable converged candidates by specialist profile.</p></div></div>'
        + '<div class="market-grid">' + market_cards + '</div>'
        + _coverage_html(manifest, policy)
        + _failed_seeds_html(manifest)
        + notes_html
        + '<p class="provenance">Historical metrics are computed only from observations earlier than this run. Future fares cannot rewrite this run\'s historical comparison.<br>Immutable evidence snapshot: <code>' + history_path + '</code></p>'
        + '</main></body></html>\n'
    )


def _render_index(entries: Sequence[tuple[Mapping[str, Any], str]]) -> str:
    rows = "".join(
        '<li><a href="runs/' + escape(slug) + '/"><strong>' + escape(str(manifest["radar_run_id"])) + '</strong><time>' + escape(str(manifest["run_at"])) + '</time></a></li>'
        for manifest, slug in reversed(entries)
    )
    latest_meta = "No Radar runs published yet."
    if entries:
        latest = entries[-1][0]
        latest_meta = f'{escape(str(latest["radar_run_id"]))}<br><span class="source">{escape(str(latest["run_at"]))}</span>'
    return (
        '<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="color-scheme" content="light"><title>Cheap Flight Radar</title><style>' + SITE_CSS + '</style></head><body><main class="shell">'
        '<div class="topbar"><a class="brand" href="./"><span class="brand-mark" aria-hidden="true">↗</span><span>Cheap Flight Radar</span></a></div>'
        '<header class="hero"><p class="eyebrow">Taiwan → World</p><h1>Cheap Flight Radar</h1><p class="hero-copy">Permanent fare intelligence reports with immutable historical evidence.</p></header>'
        '<div class="index-hero"><section class="latest-card"><p class="eyebrow">Latest Radar</p><h2>Most recent published run</h2><p>' + latest_meta + '</p>'
        + ('<a class="latest-link" href="latest/">Open latest report</a>' if entries else '')
        + '</section><section class="archive-card"><p class="eyebrow">Archive</p><h2>Permanent runs</h2><p class="hero-copy">Each URL preserves that run\'s historical meaning.</p></section></div>'
        '<section class="archive-card" style="margin-top:14px"><h2>Run history</h2><ul class="run-list">' + rows + '</ul></section>'
        '</main></body></html>\n'
    )


def build_site(*, policy_path: Path, history_dir: Path, manifest_dir: Path, site_dir: Path) -> tuple[Path, ...]:
    policy = load_policy(policy_path)
    snapshots = load_history_snapshots(history_dir)
    all_history = _history_observations(snapshots)
    manifests = [load_manifest(path) for path in sorted(manifest_dir.glob("*.json"))]
    manifests.sort(key=lambda item: (_parse_datetime(str(item["run_at"])), str(item["radar_run_id"])))
    if site_dir.exists():
        shutil.rmtree(site_dir)
    site_dir.mkdir(parents=True)
    (site_dir / ".nojekyll").write_text("", encoding="utf-8")
    entries: list[tuple[Mapping[str, Any], str]] = []
    outputs: list[Path] = []
    for manifest in manifests:
        snapshot = _snapshot_for_manifest(manifest, history_dir)
        slug = safe_run_id(snapshot.radar_run_id)
        run_dir = site_dir / "runs" / slug
        run_dir.mkdir(parents=True, exist_ok=True)
        page = run_dir / "index.html"
        page.write_text(render_run_page(manifest, snapshot, all_history, policy), encoding="utf-8")
        outputs.append(page)
        entries.append((manifest, slug))
    index = site_dir / "index.html"
    index.write_text(_render_index(entries), encoding="utf-8")
    outputs.append(index)
    latest_dir = site_dir / "latest"
    latest_dir.mkdir(parents=True, exist_ok=True)
    latest = latest_dir / "index.html"
    if entries:
        latest_slug = entries[-1][1]
        latest.write_bytes((site_dir / "runs" / latest_slug / "index.html").read_bytes())
    else:
        latest.write_text("<!doctype html><html><body><p>No Radar runs published.</p></body></html>\n", encoding="utf-8")
    outputs.append(latest)
    return tuple(outputs)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Cheap Flight Radar static publication")
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--history-dir", type=Path, required=True)
    parser.add_argument("--manifest-dir", type=Path, required=True)
    parser.add_argument("--site-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    build_site(policy_path=args.policy, history_dir=args.history_dir, manifest_dir=args.manifest_dir, site_dir=args.site_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
