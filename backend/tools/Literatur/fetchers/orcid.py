"""Fetcher untuk ORCID Public API — author identity & published works.

Base: https://pub.orcid.org/v3.0/
Auth: OAuth for Public API (free). For read-only, no auth needed for
public profiles.

Useful for:
  - Disambiguating authors
  - Finding all works by an author
  - Getting researcher profiles (affiliation, funding, peer-review)

Env: ORCID_CLIENT_ID + ORCID_CLIENT_SECRET for higher rate limits
"""

import logging
import os
from typing import Iterable

from ..http_client import RateLimiter, fetch_json
from ..paper import Paper

PUB_API = "https://pub.orcid.org/v3.0"

log = logging.getLogger(__name__)


def _parse_work(work: dict, orcid: str) -> Paper | None:
    """Parse ORCID work summary into Paper."""
    title_info = work.get("title") or {}
    title = title_info.get("title", {}).get("value")
    if not title:
        return None

    # External IDs
    doi = None
    ext_ids = work.get("external-ids") or {}
    for eid in ext_ids.get("external-id") or []:
        if eid.get("external-id-type") == "doi":
            doi = eid.get("external-id-value")
            break

    year = None
    pub_date = work.get("publication-date") or {}
    if pub_date:
        y = pub_date.get("year", {}).get("value")
        if y:
            try:
                year = int(y)
            except (ValueError, TypeError):
                pass

    work_type = work.get("type")

    # Journal title
    journal = work.get("journal-title") or {}
    venue = journal.get("value") if isinstance(journal, dict) else None

    # URL
    url = work.get("url") or {}
    landing = url.get("value") if isinstance(url, dict) else None
    if not landing and doi:
        landing = f"https://doi.org/{doi}"

    return Paper(
        source="orcid",
        source_id=f"{orcid}:{work.get('put-code', '')}",
        title=title,
        authors=[orcid],  # ORCID is the author identifier
        abstract=None,  # ORCID work summaries don't include abstracts
        year=year,
        venue=venue,
        venue_type=None,
        doi=doi,
        url=landing,
        pdf_url=landing,
        citations=None,
        is_open_access=None,
        type=work_type,
    )


def get_author_works(client, orcid: str, limit: int = 25) -> Iterable[Paper]:
    """Get all works for an ORCID identifier.

    Args:
        orcid: ORCID ID (e.g. "0000-0002-1825-0097")
    """
    rl = RateLimiter(0.3)
    rl.wait()

    url = f"{PUB_API}/{orcid}/works"
    headers = {"Accept": "application/json"}

    data = fetch_json(client, url, headers=headers)
    if not data:
        return

    groups = data.get("group", [])
    fetched = 0

    for group in groups:
        summaries = group.get("work-summary", [])
        if not summaries:
            continue

        # Use the first (preferred) summary
        paper = _parse_work(summaries[0], orcid)
        if paper:
            # Enrich abstract via DOI → OpenAlex
            if paper.doi:
                from .openalex import enrich_abstract_via_doi
                paper.abstract = enrich_abstract_via_doi(paper.doi, client)
            yield paper
            fetched += 1
            if fetched >= limit:
                return


def get_author_profile(client, orcid: str) -> dict | None:
    """Get researcher profile from ORCID."""
    rl = RateLimiter(0.3)
    rl.wait()

    url = f"{PUB_API}/{orcid}/person"
    headers = {"Accept": "application/json"}

    data = fetch_json(client, url, headers=headers)
    if not data:
        return None

    name = data.get("name") or {}
    given = name.get("given-names", {}).get("value", "")
    family = name.get("family-name", {}).get("value", "")

    employments = []
    emp_data = data.get("employments", {})
    for emp in emp_data.get("employment", []):
        org = emp.get("organization") or {}
        employments.append({
            "organization": org.get("name"),
            "role": emp.get("role-title"),
            "department": emp.get("department-name"),
        })

    return {
        "orcid": orcid,
        "name": f"{given} {family}".strip(),
        "given_name": given,
        "family_name": family,
        "employments": employments,
    }


def search(client, query: str, limit: int = 25, filters: dict | None = None) -> Iterable[Paper]:
    """Search ORCID by author name — returns works from matching profiles.

    First searches ORCID for researchers matching the query, then fetches
    their works.
    """
    rl = RateLimiter(0.3)

    # Search for researchers
    rl.wait()
    search_url = "https://pub.orcid.org/v3.0/expanded-search"
    params = {
        "q": query,
        "rows": min(5, limit),
    }
    headers = {"Accept": "application/json"}

    data = fetch_json(client, search_url, params=params, headers=headers)
    if not data:
        return

    results = data.get("expanded-result", [])
    if not results:
        return

    fetched = 0
    for result in results:
        orcid = result.get("orcid-id")
        if not orcid:
            continue

        remaining = limit - fetched
        if remaining <= 0:
            return

        for paper in get_author_works(client, orcid, remaining):
            # Set real author names from the work
            given = result.get("given-names", "")
            family = result.get("family-names", "")
            if given or family:
                paper.authors = [f"{given} {family}".strip()]
            yield paper
            fetched += 1
            if fetched >= limit:
                return
