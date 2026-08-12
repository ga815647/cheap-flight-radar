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
    required = (
        "radar_run_id",
        "run_at",
        "history_snapshot_path",
        "sections",
        "markets",
        "coverage",
    )
    for key in required:
        if key not in raw:
            raise ValueError(f"publication manifest missing {key!r}")
    _parse_datetime(str(raw["run_at"]))
    safe_run_id(str(raw["radar_run_id"]))
    return raw


def load_history_snapshots(
    history_dir: Path,
) -> tuple[FareHistorySnapshot, ...]:
    root = history_dir / "data" / "price-history"
    if not root.exists():
        return ()
    snapshots = [
        snapshot_from_json(path.read_text(encoding="utf-8"))
        for path in sorted(root.rglob("*.json"))
    ]
    return tuple(
        sorted(
            snapshots,
            key=lambda item: (_parse_datetime(item.run_at), item.radar_run_id),
        )
    )


def _history_observations(
    snapshots: Sequence[FareHistorySnapshot],
) -> tuple[FareObservation, ...]:
    return tuple(
        observation
        for snapshot in snapshots
        for observation in snapshot.observations
    )


def _snapshot_for_manifest(
    manifest: Mapping[str, Any],
    history_dir: Path,
) -> FareHistorySnapshot:
    relative = Path(str(manifest["history_snapshot_path"]))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("history_snapshot_path must stay inside history_dir")
    snapshot = snapshot_from_json(
        (history_dir / relative).read_text(encoding="utf-8")
    )
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


def _candidate_details(
    manifest: Mapping[str, Any],
    observation_id: str,
) -> Mapping[str, Any]:
    details = manifest.get("candidate_details", {})
    if not isinstance(details, Mapping):
        raise TypeError("candidate_details must be a mapping")
    item = details.get(observation_id, {})
    if not isinstance(item, Mapping):
        raise TypeError("candidate detail must be a mapping")
    return item


def _history_lines(comparison: FareHistoryComparison) -> list[str]:
    lines = [
        f"Comparable samples: {comparison.sample_count} · "
        f"confidence: {comparison.confidence}"
    ]
    if comparison.all_time_low_twd is None:
        lines.append("Historical/rolling low: no prior comparable observation")
    else:
        lines.append(
            f"Prior all-time comparable low: "
            f"{_money(comparison.all_time_low_twd)}"
        )
        for days in sorted(comparison.rolling_lows_twd):
            statistic = comparison.rolling_lows_twd[days]
            if statistic.value is not None:
                lines.append(
                    f"{days}-day rolling low: {_money(statistic.value)} "
                    f"({statistic.sample_count} samples)"
                )

    if comparison.selected_baseline_twd is None:
        lines.append("Recent baseline: insufficient comparable history")
    else:
        lines.append(
            f"Recent baseline: {_money(comparison.selected_baseline_twd)} "
            f"({comparison.selected_baseline_window_days}-day median)"
        )
        lines.append(
            "Percent below recent baseline: "
            f"{_percent(comparison.percent_below_baseline)}"
        )

    if comparison.historical_percentile is not None:
        lines.append(
            f"Historical percentile: "
            f"{comparison.historical_percentile:.1f}th"
        )
    if comparison.confidence in {"none", "sparse", "low"}:
        lines.append(
            "Sparse-history note: evidence density is limited; "
            "do not infer a precise market percentile."
        )
    if comparison.anomaly_label:
        lines.append(f"Historical label: {comparison.anomaly_label}")
    return lines


def _candidate_html(
    observation: FareObservation,
    comparison: FareHistoryComparison,
    manifest: Mapping[str, Any],
    policy: Mapping[str, Any],
) -> str:
    details = _candidate_details(manifest, observation.observation_id)
    origin = _airport_label(observation.origin, policy)
    return_date = details.get("return_date")
    date_text = observation.departure_date
    if return_date:
        date_text += f" → {return_date}"
    title = details.get("title") or f"{origin} → {observation.destination}"
    history = "".join(
        f"<li>{escape(line)}</li>" for line in _history_lines(comparison)
    )
    return (
        '<article class="candidate">'
        f"<h3>{escape(str(title))}</h3>"
        f'<p class="price">{escape(_money(observation.normalized_twd_price))}</p>'
        f"<p>{escape(date_text)} · {escape(observation.trip_type)} · "
        f"{escape(observation.verification_state)}</p>"
        f'<p class="source">Evidence: {escape(observation.source_id)}</p>'
        f'<ul class="history">{history}</ul>'
        "</article>"
    )


def _section_candidate(
    title: str,
    observation: FareObservation | None,
    comparisons: Mapping[str, FareHistoryComparison],
    manifest: Mapping[str, Any],
    policy: Mapping[str, Any],
    *,
    empty_text: str = "No converged candidate for this view in this run.",
) -> str:
    if observation is None:
        content = f'<p class="empty">{escape(empty_text)}</p>'
    else:
        content = _candidate_html(
            observation,
            comparisons[observation.observation_id],
            manifest,
            policy,
        )
    return f"<section><h2>{escape(title)}</h2>{content}</section>"


def _market_section(
    title: str,
    ids: Sequence[str],
    by_id: Mapping[str, FareObservation],
    comparisons: Mapping[str, FareHistoryComparison],
    manifest: Mapping[str, Any],
    policy: Mapping[str, Any],
) -> str:
    if not ids:
        body = '<p class="empty">No notable converged candidate in this run.</p>'
    else:
        body = "".join(
            _candidate_html(
                by_id[observation_id],
                comparisons[observation_id],
                manifest,
                policy,
            )
            for observation_id in ids
        )
    return f"<section><h2>{escape(title)}</h2>{body}</section>"


def _failed_seeds_html(manifest: Mapping[str, Any]) -> str:
    seeds = manifest.get("failed_seeds", [])
    if not seeds:
        body = '<p class="empty">No failed cheap seeds recorded.</p>'
    else:
        rows: list[str] = []
        for seed in seeds:
            if not isinstance(seed, Mapping):
                raise TypeError("failed seed must be a mapping")
            route = str(seed.get("route", "unknown route"))
            price = str(seed.get("price", "price unknown"))
            reason = str(seed.get("reason", "did not converge"))
            rows.append(
                f"<li><strong>{escape(route)}</strong> · {escape(price)} — "
                f"{escape(reason)}</li>"
            )
        body = "<ul>" + "".join(rows) + "</ul>"
    return (
        "<section><h2>Failed / Non-converged Cheap Seeds</h2>"
        f"{body}</section>"
    )


def _coverage_html(
    manifest: Mapping[str, Any],
    policy: Mapping[str, Any],
) -> str:
    coverage = manifest["coverage"]
    if not isinstance(coverage, Mapping):
        raise TypeError("coverage must be a mapping")

    origins = coverage.get("origins", {})
    origin_rows = ""
    if isinstance(origins, Mapping):
        origin_rows = "".join(
            f"<li>{escape(str(origin))}: {escape(str(state))}</li>"
            for origin, state in sorted(origins.items())
        )

    registry = policy["public_intelligence"]["fixed_watch_registry"]
    cadence = {str(item["id"]): item["cadence_hours"] for item in registry}
    fixed = coverage.get("fixed_watch", {})
    fixed_status = (
        fixed.get("status", "unknown")
        if isinstance(fixed, Mapping)
        else "unknown"
    )
    source_rows: list[str] = []
    if isinstance(fixed, Mapping):
        for item in fixed.get("sources", []):
            source_id = str(item.get("id", "unknown"))
            state = str(item.get("state", "unknown"))
            threshold = cadence.get(source_id)
            threshold_text = (
                f" · freshness threshold {threshold}h"
                if threshold is not None
                else ""
            )
            source_rows.append(
                f"<li>{escape(source_id)}: {escape(state)}"
                f"{escape(threshold_text)}</li>"
            )

    china = coverage.get("china", {})
    china_status = (
        china.get("status", "unknown")
        if isinstance(china, Mapping)
        else "unknown"
    )
    china_rows: list[str] = []
    if isinstance(china, Mapping):
        modes = china.get("modes", {})
        if isinstance(modes, Mapping):
            china_rows = [
                f"<li>{escape(str(mode))}: {escape(str(state))}</li>"
                for mode, state in sorted(modes.items())
            ]

    return (
        "<section><h2>Coverage &amp; Freshness</h2>"
        "<h3>Origin coverage</h3><ul>"
        + origin_rows
        + "</ul>"
        + f"<h3>Fixed-watch coverage: {escape(str(fixed_status))}</h3><ul>"
        + "".join(source_rows)
        + "</ul>"
        + f"<h3>China-mode coverage: {escape(str(china_status))}</h3><ul>"
        + "".join(china_rows)
        + "</ul></section>"
    )


def _validate_market_ids(
    markets: Mapping[str, Any],
    by_id: Mapping[str, FareObservation],
) -> None:
    for market_name, ids in markets.items():
        if not isinstance(ids, Sequence) or isinstance(ids, (str, bytes)):
            raise TypeError(
                f"market {market_name!r} candidates must be a sequence"
            )
        missing = [item for item in ids if item not in by_id]
        if missing:
            raise ValueError(
                f"market {market_name!r} references unknown observations: "
                f"{missing}"
            )


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
        near_term_days=int(
            policy["search"]["price_time_views"]["near_term"][
                "departure_within_days"
            ]
        ),
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
            raise ValueError(
                f"section {name!r} references unknown observation "
                f"{observation_id!r}"
            )
        return observation

    best_short_break = selected("best_short_break")
    unusual_long_haul = selected("unusual_long_haul_deal")

    displayed_ids = {
        item.observation_id
        for item in (
            floors.horizon_absolute,
            floors.near_term,
            best_short_break,
            unusual_long_haul,
        )
        if item is not None
    }
    for ids in markets.values():
        displayed_ids.update(str(item) for item in ids)

    comparisons = {
        observation_id: compare_with_history(
            by_id[observation_id],
            all_history,
            policy["price_history"],
        )
        for observation_id in displayed_ids
    }

    body = [
        _section_candidate(
            "Absolute Cheapest",
            floors.horizon_absolute,
            comparisons,
            manifest,
            policy,
        ),
        _section_candidate(
            "Near-Term Cheapest",
            floors.near_term,
            comparisons,
            manifest,
            policy,
        ),
        _section_candidate(
            "Best Short Break",
            best_short_break,
            comparisons,
            manifest,
            policy,
        ),
        _section_candidate(
            "Unusual Long-Haul Deal",
            unusual_long_haul,
            comparisons,
            manifest,
            policy,
            empty_text=str(
                manifest.get(
                    "unusual_long_haul_empty_reason",
                    "No converged unusual long-haul deal in this run.",
                )
            ),
        ),
        _market_section(
            "Japan Notable Candidates",
            list(markets.get("japan", [])),
            by_id,
            comparisons,
            manifest,
            policy,
        ),
        _market_section(
            "Korea Notable Candidates",
            list(markets.get("korea", [])),
            by_id,
            comparisons,
            manifest,
            policy,
        ),
        _market_section(
            "China Notable Candidates",
            list(markets.get("china", [])),
            by_id,
            comparisons,
            manifest,
            policy,
        ),
        _market_section(
            "World Notable Candidates",
            list(markets.get("world", [])),
            by_id,
            comparisons,
            manifest,
            policy,
        ),
        _failed_seeds_html(manifest),
        _coverage_html(manifest, policy),
    ]

    notes = manifest.get("notes", [])
    if notes:
        body.append(
            "<section><h2>Run Notes</h2><ul>"
            + "".join(
                f"<li>{escape(str(note))}</li>" for note in notes
            )
            + "</ul></section>"
        )

    css = (
        ':root{font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",'
        'sans-serif;color:#17202a;background:#f7f8fa}'
        "body{max-width:1080px;margin:0 auto;padding:2rem 1rem 4rem}"
        "header,section{background:white;border:1px solid #e4e7eb;"
        "border-radius:14px;padding:1.25rem 1.4rem;margin:1rem 0}"
        "h1,h2,h3{line-height:1.2}h1{margin:.2rem 0}"
        ".meta,.source,.empty{color:#5f6b76}"
        ".candidate{border-top:1px solid #edf0f2;padding:1rem 0}"
        ".candidate:first-of-type{border-top:0}"
        ".price{font-size:1.35rem;font-weight:700;margin:.3rem 0}"
        ".history{line-height:1.55}a{color:inherit}code{word-break:break-all}"
    )
    run_title = f"Cheap Flight Radar — {snapshot.radar_run_id}"
    history_path = escape(str(manifest["history_snapshot_path"]))
    return (
        '<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{escape(run_title)}</title><style>{css}</style></head><body>"
        f"<header><h1>{escape(run_title)}</h1>"
        f'<p class="meta">Run at {escape(snapshot.run_at)} · '
        f"immutable evidence snapshot <code>{history_path}</code></p>"
        '<p class="meta">Historical metrics are computed only from observations '
        "earlier than this run. Future fares cannot rewrite this run's "
        "historical comparison.</p></header>"
        + "".join(body)
        + "</body></html>\n"
    )


def _render_index(
    entries: Sequence[tuple[Mapping[str, Any], str]],
) -> str:
    rows = "".join(
        f'<li><a href="runs/{escape(slug)}/">'
        f'{escape(str(manifest["radar_run_id"]))}</a> · '
        f'{escape(str(manifest["run_at"]))}</li>'
        for manifest, slug in reversed(entries)
    )
    return (
        '<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>Cheap Flight Radar</title></head><body>"
        "<h1>Cheap Flight Radar</h1>"
        '<p><a href="latest/">Latest Radar</a></p>'
        "<h2>Permanent runs</h2><ul>"
        + rows
        + "</ul></body></html>\n"
    )


def build_site(
    *,
    policy_path: Path,
    history_dir: Path,
    manifest_dir: Path,
    site_dir: Path,
) -> tuple[Path, ...]:
    policy = load_policy(policy_path)
    snapshots = load_history_snapshots(history_dir)
    all_history = _history_observations(snapshots)
    manifests = [
        load_manifest(path)
        for path in sorted(manifest_dir.glob("*.json"))
    ]
    manifests.sort(
        key=lambda item: (
            _parse_datetime(str(item["run_at"])),
            str(item["radar_run_id"]),
        )
    )

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
        page.write_text(
            render_run_page(manifest, snapshot, all_history, policy),
            encoding="utf-8",
        )
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
        latest.write_bytes(
            (site_dir / "runs" / latest_slug / "index.html").read_bytes()
        )
    else:
        latest.write_text(
            "<!doctype html><html><body>"
            "<p>No Radar runs published.</p></body></html>\n",
            encoding="utf-8",
        )
    outputs.append(latest)
    return tuple(outputs)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build Cheap Flight Radar static publication"
    )
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--history-dir", type=Path, required=True)
    parser.add_argument("--manifest-dir", type=Path, required=True)
    parser.add_argument("--site-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    build_site(
        policy_path=args.policy,
        history_dir=args.history_dir,
        manifest_dir=args.manifest_dir,
        site_dir=args.site_dir,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
