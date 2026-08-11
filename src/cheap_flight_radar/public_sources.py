"""Fixture-testable parsers for the v0 fixed public-intelligence sources."""

from __future__ import annotations

from datetime import datetime
import re
from urllib.parse import urljoin, urlparse

from parsel import Selector

from .public_intelligence import DiscoverySighting, FixedWatch, make_observation_id


class ParseContractError(ValueError):
    """Raised when a fetched page no longer satisfies a source parser contract."""


PROMO_RE = re.compile(
    r"(?:促銷|優惠|特價|限時|開賣|sale|promo(?:tion)?|discount|fare\s+sale|"
    r"(?:TWD|NT\$|NTD|[$¥￥])\s*\d[\d,]*|\b\d{3,6}\s*元(?:起)?)",
    re.IGNORECASE,
)
PRICE_RE = re.compile(
    r"(?:NT\$|TWD\s*|NTD\s*|[$¥￥])\s*\d[\d,]*|\b\d{3,6}\s*元",
    re.IGNORECASE,
)
ROUTE_PRICE_RE = re.compile(r"\b[A-Z]{3}\s+[A-Z]{3}\b|\b[A-Z]{3}\s*[-–]\s*[A-Z]{3}\b")


def parse_source_html(
    watch: FixedWatch,
    html: str,
    response_url: str,
    observed_at: datetime,
) -> tuple[DiscoverySighting, ...]:
    if not html.strip():
        raise ParseContractError(f"{watch.id}: empty document")
    if watch.id == "ptt_japan_travel_info":
        return _parse_ptt(watch, html, response_url, observed_at)
    if watch.id == "tigerair_tw_official":
        return _parse_airline(watch, html, response_url, observed_at, carrier="Tigerair Taiwan")
    if watch.id == "china_airlines_official":
        return _parse_airline(watch, html, response_url, observed_at, carrier="China Airlines")
    raise ParseContractError(f"no parser registered for {watch.id}")


def _parse_airline(
    watch: FixedWatch,
    html: str,
    response_url: str,
    observed_at: datetime,
    *,
    carrier: str,
) -> tuple[DiscoverySighting, ...]:
    selector = Selector(text=html, type="html")
    anchors = selector.xpath("//a[@href]")
    if not anchors:
        raise ParseContractError(f"{watch.id}: expected public navigation/promotion links")

    sightings: list[DiscoverySighting] = []
    seen_urls: set[str] = set()
    for anchor in anchors:
        href = (anchor.attrib.get("href") or "").strip()
        if not href or href.startswith(("javascript:", "mailto:", "tel:")):
            continue
        text_bits = anchor.xpath(".//text() | .//img/@alt | .//@title | .//@aria-label").getall()
        title = _normalize_text(" ".join(text_bits))
        if not title or not PROMO_RE.search(title):
            continue
        item_url = urljoin(response_url, href)
        if watch.id == "china_airlines_official" and not _china_airlines_signal(item_url, title):
            continue
        if item_url in seen_urls:
            continue
        seen_urls.add(item_url)
        sightings.append(
            DiscoverySighting(
                observation_id=make_observation_id(watch.id, item_url, title, observed_at),
                source_id=watch.id,
                source_url=response_url,
                item_url=item_url,
                observed_at=observed_at,
                title=title,
                carrier=carrier,
                price_text=_price_text(title),
            )
        )
    return tuple(sightings)


def _china_airlines_signal(item_url: str, title: str) -> bool:
    parsed = urlparse(item_url)
    host = parsed.netloc.casefold()
    path = parsed.path.casefold().rstrip("/")
    if host == "flights.china-airlines.com":
        return bool(PRICE_RE.search(title) and ROUTE_PRICE_RE.search(title.upper()))
    prefix = "/tw/zh/itinerary-booking/exclusive-offers/latest-events/"
    return host.endswith("china-airlines.com") and path.startswith(prefix.rstrip("/")) and path != prefix.rstrip("/")


def _parse_ptt(
    watch: FixedWatch,
    html: str,
    response_url: str,
    observed_at: datetime,
) -> tuple[DiscoverySighting, ...]:
    selector = Selector(text=html, type="html")
    rows = selector.css(".r-ent")
    if not rows:
        raise ParseContractError(f"{watch.id}: expected .r-ent board rows")

    sightings: list[DiscoverySighting] = []
    for row in rows:
        anchor = row.css(".title a")
        if not anchor:
            continue
        title = _normalize_text(" ".join(anchor.xpath(".//text()").getall()))
        if not (title.startswith("[資訊]") or title.startswith("［資訊］")):
            continue
        if not PROMO_RE.search(title):
            continue
        href = (anchor.attrib.get("href") or "").strip()
        if not href:
            continue
        item_url = urljoin(response_url, href)
        sightings.append(
            DiscoverySighting(
                observation_id=make_observation_id(watch.id, item_url, title, observed_at),
                source_id=watch.id,
                source_url=response_url,
                item_url=item_url,
                observed_at=observed_at,
                title=title,
                price_text=_price_text(title),
            )
        )
    return tuple(sightings)


def _normalize_text(value: str) -> str:
    return " ".join(value.split())


def _price_text(value: str) -> str | None:
    match = PRICE_RE.search(value)
    return match.group(0).strip() if match else None
