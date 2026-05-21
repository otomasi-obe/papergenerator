"""Fetcher untuk IEEE Xplore - https://ieeexploreapi.ieee.org/api/v1/search/articles

API key gratis tapi wajib (https://developer.ieee.org). Kalau IEEE_API_KEY
tidak diset, fetcher me-skip diam-diam (tidak crash) supaya pipeline SLR
tetap jalan dengan source lainnya.
"""
import os
from typing import Iterable
from ..http_client import RateLimiter, fetch_json
from ..paper import Paper

BASE = "https://ieeexploreapi.ieee.org/api/v1/search/articles"


def _parse_article(a: dict) -> Paper | None:
    title = (a.get("title") or "").strip()
    if not title:
        return None

    authors_block = (a.get("authors") or {}).get("authors") or []
    authors = [au.get("full_name") for au in authors_block if au.get("full_name")][:8]

    year = None
    if a.get("publication_year"):
        try:
            year = int(a["publication_year"])
        except (ValueError, TypeError):
            pass

    venue = a.get("publication_title") or None
    pub_type = (a.get("content_type") or "").lower()
    venue_type = None
    if pub_type:
        if "conference" in pub_type:
            venue_type = "conference"
        elif "journal" in pub_type or "magazine" in pub_type or "transactions" in pub_type:
            venue_type = "journal"
        elif "early access" in pub_type:
            venue_type = "preprint"

    article_num = a.get("article_number")
    return Paper(
        source="ieee",
        source_id=str(article_num or a.get("doi") or ""),
        title=title,
        authors=authors,
        abstract=a.get("abstract"),
        year=year,
        venue=venue,
        venue_type=venue_type,
        doi=a.get("doi"),
        url=a.get("html_url") or (article_num and f"https://ieeexplore.ieee.org/document/{article_num}") or None,
        citations=a.get("citing_paper_count"),
        is_open_access=bool(a.get("open_access_flag")),
        type=pub_type or None,
        publisher="IEEE",
    )


def search(client, query: str, limit: int = 25,
           filters: dict | None = None) -> Iterable[Paper]:
    api_key = os.getenv("IEEE_API_KEY")
    if not api_key:
        # No API key: skip silently. Other sources still produce IEEE-published
        # papers via OpenAlex/Crossref/DBLP, just without IEEE-native metadata.
        return iter([])

    rl = RateLimiter(0.4)
    per_page = min(limit, 200)
    fetched = 0
    start_record = 1  # IEEE uses 1-based start_record

    params_base = {
        "apikey": api_key,
        "querytext": query,
        "format": "json",
        "max_records": min(per_page, limit - fetched),
        "start_record": start_record,
        "sort_field": "article_title",
        "sort_order": "asc",
    }
    if filters:
        if filters.get("year_from"):
            params_base["start_year"] = filters["year_from"]
        if filters.get("year_to"):
            params_base["end_year"] = filters["year_to"]
        if filters.get("open_access"):
            params_base["open_access"] = "True"

    while fetched < limit:
        rl.wait()
        params = dict(params_base, max_records=min(per_page, limit - fetched),
                      start_record=start_record)
        data = fetch_json(client, BASE, params=params)
        if not data:
            return
        articles = data.get("articles") or []
        if not articles:
            return
        for art in articles:
            paper = _parse_article(art)
            if paper:
                yield paper
                fetched += 1
                if fetched >= limit:
                    return
        total_records = int(data.get("total_records") or 0)
        start_record += len(articles)
        if start_record > total_records:
            return
