"""Scrapy-backed execution backend for due fixed public-intelligence watches."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime
import json
from pathlib import Path
from typing import Any

import scrapy
from scrapy.crawler import CrawlerProcess

from .public_intelligence import (
    DiscoverySighting,
    FixedWatch,
    FixedWatchAttempt,
    FixedWatchRunManifest,
    load_fixed_watch_registry,
    make_attempt_id,
    utc_now,
)
from .public_sources import ParseContractError, parse_source_html


BLOCKED_HTTP = {401, 403, 429}
UNAVAILABLE_HTTP = {404, 410}


class FixedWatchSpider(scrapy.Spider):
    name = "cheap-flight-radar-fixed-watch"
    custom_settings = {
        "RETRY_TIMES": 2,
        "COOKIES_ENABLED": True,
        "TELNETCONSOLE_ENABLED": False,
        "LOG_LEVEL": "INFO",
        "USER_AGENT": "cheap-flight-radar/0.1 public-source-monitor (+https://github.com/ga815647/cheap-flight-radar)",
        "DOWNLOAD_TIMEOUT": 35,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 2,
    }

    def __init__(
        self,
        *,
        run_id: str,
        watches: tuple[FixedWatch, ...],
        output_path: str,
        requested_at: datetime,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.run_id = run_id
        self.watches = watches
        self.output_path = Path(output_path)
        self.requested_at = requested_at
        self.attempts: dict[str, FixedWatchAttempt] = {}
        self.observations: list[DiscoverySighting] = []
        self.started_at: dict[str, datetime] = {}

    async def start(self):
        for watch in self.watches:
            started_at = utc_now()
            self.started_at[watch.id] = started_at
            if watch.acquisition != "direct_http":
                self._record_attempt(
                    watch,
                    status="unavailable",
                    started_at=started_at,
                    completed_at=utc_now(),
                    error="current production workflow supports direct_http fixed watches only; JS fallback is opt-in",
                )
                continue
            yield scrapy.Request(
                watch.entry_url,
                callback=self.parse_watch,
                errback=self.errback_watch,
                cb_kwargs={"watch": watch},
                dont_filter=True,
                meta={"handle_httpstatus_all": True},
            )

    def parse_watch(self, response: scrapy.http.Response, watch: FixedWatch):
        started_at = self.started_at[watch.id]
        completed_at = utc_now()
        status = response.status
        if status in BLOCKED_HTTP:
            self._record_attempt(
                watch,
                status="blocked",
                started_at=started_at,
                completed_at=completed_at,
                final_url=response.url,
                http_status=status,
                error=f"HTTP {status}",
            )
            return
        if status in UNAVAILABLE_HTTP:
            self._record_attempt(
                watch,
                status="unavailable",
                started_at=started_at,
                completed_at=completed_at,
                final_url=response.url,
                http_status=status,
                error=f"HTTP {status}",
            )
            return
        if status >= 400:
            self._record_attempt(
                watch,
                status="fetch_failed",
                started_at=started_at,
                completed_at=completed_at,
                final_url=response.url,
                http_status=status,
                error=f"HTTP {status}",
            )
            return

        try:
            observations = parse_source_html(watch, response.text, response.url, completed_at)
        except ParseContractError as exc:
            self._record_attempt(
                watch,
                status="parse_failed",
                started_at=started_at,
                completed_at=completed_at,
                final_url=response.url,
                http_status=status,
                error=str(exc),
            )
            return

        self.observations.extend(observations)
        self._record_attempt(
            watch,
            status="success",
            started_at=started_at,
            completed_at=completed_at,
            final_url=response.url,
            http_status=status,
            observation_count=len(observations),
        )

    def errback_watch(self, failure):
        watch = failure.request.cb_kwargs["watch"]
        self._record_attempt(
            watch,
            status="fetch_failed",
            started_at=self.started_at[watch.id],
            completed_at=utc_now(),
            final_url=getattr(failure.request, "url", None),
            error=failure.getErrorMessage(),
        )

    def closed(self, reason: str) -> None:
        completed_at = utc_now()
        for watch in self.watches:
            if watch.id not in self.attempts:
                started_at = self.started_at.get(watch.id, self.requested_at)
                self._record_attempt(
                    watch,
                    status="fetch_failed",
                    started_at=started_at,
                    completed_at=completed_at,
                    error=f"crawler closed without a terminal attempt: {reason}",
                )
        ordered_attempts = tuple(self.attempts[watch.id] for watch in self.watches)
        manifest = FixedWatchRunManifest(
            run_id=self.run_id,
            requested_at=self.requested_at,
            completed_at=completed_at,
            requested_watch_ids=tuple(watch.id for watch in self.watches),
            attempts=ordered_attempts,
            observations=tuple(self.observations),
        )
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_text(
            json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _record_attempt(
        self,
        watch: FixedWatch,
        *,
        status: str,
        started_at: datetime,
        completed_at: datetime,
        final_url: str | None = None,
        http_status: int | None = None,
        error: str | None = None,
        observation_count: int = 0,
    ) -> None:
        self.attempts[watch.id] = FixedWatchAttempt(
            attempt_id=make_attempt_id(self.run_id, watch.id, started_at),
            source_id=watch.id,
            status=status,
            started_at=started_at,
            completed_at=completed_at,
            requested_url=watch.entry_url,
            final_url=final_url,
            http_status=http_status,
            error=error,
            observation_count=observation_count,
        )


def _select_watches(all_watches: tuple[FixedWatch, ...], watch_ids: str) -> tuple[FixedWatch, ...]:
    requested = tuple(dict.fromkeys(value.strip() for value in watch_ids.split(",") if value.strip()))
    if not requested:
        raise SystemExit("--watch-ids must contain at least one fixed-watch id")
    by_id = {watch.id: watch for watch in all_watches}
    missing = [source_id for source_id in requested if source_id not in by_id]
    if missing:
        raise SystemExit(f"unknown fixed-watch ids: {', '.join(missing)}")
    return tuple(by_id[source_id] for source_id in requested)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--watch-ids", required=True, help="comma-separated fixed-watch ids chosen by the ChatGPT orchestrator")
    parser.add_argument("--output", required=True)
    parser.add_argument("--policy", default="flight-radar.yaml")
    args = parser.parse_args(argv)

    registry = load_fixed_watch_registry(args.policy)
    watches = _select_watches(registry, args.watch_ids)
    requested_at = utc_now()
    process = CrawlerProcess()
    process.crawl(
        FixedWatchSpider,
        run_id=args.run_id,
        watches=watches,
        output_path=args.output,
        requested_at=requested_at,
    )
    process.start()
    if not Path(args.output).exists():
        raise SystemExit("fixed-watch crawler exited without writing a manifest")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
