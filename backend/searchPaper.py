"""
searchPaper.py — multi-source academic search.

Sources are split into 3 tiers:

  TIER 1 — FREE, NO API KEY REQUIRED (the default set)
    openalex, crossref, arxiv, semanticscholar, europepmc, pubmed, doaj,
    dblp, openaire, hal, plos, biorxiv, fatcat, zenodo, datacite, osf,
    paperswithcode, inspirehep, eric

  TIER 2 — FREE BUT KEY REQUIRED  (skipped gracefully if env var missing)
    core (CORE_API_KEY), lens (LENS_TOKEN), s2_keyed (SEMANTIC_SCHOLAR_KEY),
    nasa_ads (NASA_ADS_TOKEN), springer (SPRINGER_API_KEY),
    ieee (IEEE_API_KEY), unpaywall (UNPAYWALL_EMAIL)

  TIER 3 — PAID / FRONTEND-ONLY (not implemented here, see LAPORAN.md)
    Scopus, Web of Science, Wiley, ScienceDirect, Dimensions, Scite.ai,
    Google Scholar, ResearchGate, Connected Papers (search), Academia.edu

Every source returns a list[dict] with these keys:
  source, title, abstract, url, pdf_url, authors, year, doi
"""

from __future__ import annotations

import os
import re
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Any, Callable, Dict, List, Optional

import requests

try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
except ImportError:
    pass


USER_AGENT = "Mozilla/5.0 (compatible; PaperSearchBot/2.0; +mailto:research@example.com)"
DEFAULT_TIMEOUT = 25
DEFAULT_LIMIT = 5
CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "research@example.com")

# ── SSRF allowlist ──────────────────────────────────────────────────────────
# Outbound HTTP from this module is restricted to academic OA sources we
# explicitly whitelist. User-controlled queries flow into URL params, but the
# host portion never comes from user input — still, defense in depth.
import ipaddress
import socket
from urllib.parse import urlparse

_ALLOWED_HOSTS = frozenset(
    {
        "api.openalex.org",
        "api.crossref.org",
        "export.arxiv.org",
        "api.semanticscholar.org",
        "europepmc.org",
        "www.ebi.ac.uk",
        "eutils.ncbi.nlm.nih.gov",
        "doaj.org",
        "dblp.org",
        "api.openaire.eu",
        "api.archives-ouvertes.fr",
        "api.plos.org",
        "api.biorxiv.org",
        "api.fatcat.wiki",
        "zenodo.org",
        "api.datacite.org",
        "api.osf.io",
        "paperswithcode.com",
        "inspirehep.net",
        "api.ies.ed.gov",
        "api.core.ac.uk",
        "api.lens.org",
        "api.adsabs.harvard.edu",
        "api.springernature.com",
        "ieeexploreapi.ieee.org",
        "api.unpaywall.org",
    }
)


def _is_safe_url(url: str) -> bool:
    try:
        u = urlparse(url)
        if u.scheme != "https":
            return False
        host = (u.hostname or "").lower()
        if host not in _ALLOWED_HOSTS:
            return False
        try:
            for fam, _, _, _, sock in socket.getaddrinfo(host, None):
                ip = ipaddress.ip_address(sock[0])
                if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                    return False
        except Exception:
            return False
        return True
    except Exception:
        return False


def _safe_get(url, *args, **kwargs):
    """Module-internal wrapper. Other modules' requests.get is untouched."""
    if not _is_safe_url(url):
        raise requests.exceptions.InvalidURL(f"refused by SSRF allowlist: {url}")
    return requests.get(url, *args, **kwargs)


def _safe_post(url, *args, **kwargs):
    if not _is_safe_url(url):
        raise requests.exceptions.InvalidURL(f"refused by SSRF allowlist: {url}")
    return requests.post(url, *args, **kwargs)


CORE_API_KEY = os.getenv("CORE_API_KEY", "")
LENS_TOKEN = os.getenv("LENS_TOKEN", "")
S2_API_KEY = os.getenv("SEMANTIC_SCHOLAR_KEY", "")
NASA_ADS_TOKEN = os.getenv("NASA_ADS_TOKEN", "")
SPRINGER_KEY = os.getenv("SPRINGER_API_KEY", "")
IEEE_KEY = os.getenv("IEEE_API_KEY", "")
UNPAYWALL_EMAIL = os.getenv("UNPAYWALL_EMAIL", "")


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
    return s


def _err(source: str, e: Exception) -> Dict:
    return {"source": source, "error": f"{type(e).__name__}: {e}"}


def _record(source: str, **kw) -> Dict:
    base = {
        "source": source,
        "title": "",
        "abstract": "",
        "url": "",
        "pdf_url": "",
        "authors": [],
        "year": None,
        "doi": "",
    }
    base.update({k: v for k, v in kw.items() if v is not None})
    return base


# ──────────────────────────────────────────────────────────────────────────
# TIER 1 — FREE, NO API KEY
# ──────────────────────────────────────────────────────────────────────────


def _reconstruct_inverted(inv: Optional[Dict]) -> str:
    if not inv:
        return ""
    pos = [(i, w) for w, idxs in inv.items() for i in idxs]
    pos.sort()
    return " ".join(w for _, w in pos)


def search_openalex(query: str, limit: int = DEFAULT_LIMIT) -> List[Dict]:
    url = "https://api.openalex.org/works"
    params = {"search": query, "per-page": limit, "mailto": CONTACT_EMAIL}
    try:
        r = _session().get(url, params=params, timeout=DEFAULT_TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return [_err("openalex", e)]

    out = []
    for w in data.get("results", []):
        authors = [a.get("author", {}).get("display_name", "") for a in w.get("authorships", [])]
        out.append(
            _record(
                "openalex",
                title=w.get("title", ""),
                abstract=_reconstruct_inverted(w.get("abstract_inverted_index")),
                url=w.get("doi") or w.get("id", ""),
                pdf_url=(w.get("primary_location") or {}).get("pdf_url", "") or "",
                authors=authors,
                year=w.get("publication_year"),
                doi=(w.get("doi") or "").replace("https://doi.org/", ""),
            )
        )
    return out


def search_crossref(query: str, limit: int = DEFAULT_LIMIT) -> List[Dict]:
    url = "https://api.crossref.org/works"
    params = {"query": query, "rows": limit, "mailto": CONTACT_EMAIL}
    try:
        r = _session().get(url, params=params, timeout=DEFAULT_TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return [_err("crossref", e)]

    out = []
    for it in data.get("message", {}).get("items", []):
        authors = [
            f"{a.get('given', '')} {a.get('family', '')}".strip()
            for a in it.get("author", []) or []
        ]
        year = None
        for k in ("published-print", "published-online", "issued"):
            dp = (it.get(k) or {}).get("date-parts")
            if dp and dp[0]:
                year = dp[0][0]
                break
        out.append(
            _record(
                "crossref",
                title=(it.get("title") or [""])[0],
                abstract=re.sub(r"<[^>]+>", "", it.get("abstract") or "").strip(),
                url=it.get("URL", ""),
                authors=authors,
                year=year,
                doi=it.get("DOI", ""),
            )
        )
    return out


def search_arxiv(query: str, limit: int = DEFAULT_LIMIT) -> List[Dict]:
    url = "http://export.arxiv.org/api/query"
    params = {
        "search_query": f"all:{query}",
        "start": 0,
        "max_results": limit,
        "sortBy": "relevance",
    }
    try:
        r = _session().get(url, params=params, timeout=DEFAULT_TIMEOUT)
        r.raise_for_status()
        root = ET.fromstring(r.content)
    except Exception as e:
        return [_err("arxiv", e)]

    ns = {"a": "http://www.w3.org/2005/Atom"}
    out = []
    for entry in root.findall("a:entry", ns):
        title = (entry.findtext("a:title", "", ns) or "").strip()
        summary = (entry.findtext("a:summary", "", ns) or "").strip()
        link = entry.findtext("a:id", "", ns) or ""
        published = entry.findtext("a:published", "", ns) or ""
        year = int(published[:4]) if published[:4].isdigit() else None
        authors = [a.findtext("a:name", "", ns) for a in entry.findall("a:author", ns)]
        pdf_url = ""
        for ln in entry.findall("a:link", ns):
            if ln.get("title") == "pdf":
                pdf_url = ln.get("href", "")
                break
        out.append(
            _record(
                "arxiv",
                title=title,
                abstract=summary,
                url=link,
                pdf_url=pdf_url,
                authors=authors,
                year=year,
            )
        )
    return out


def search_semantic_scholar(query: str, limit: int = DEFAULT_LIMIT) -> List[Dict]:
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {
        "query": query,
        "limit": limit,
        "fields": "title,abstract,authors,year,externalIds,openAccessPdf,url",
    }
    headers = {"User-Agent": USER_AGENT}
    if S2_API_KEY:
        headers["x-api-key"] = S2_API_KEY

    last_err: Optional[Exception] = None
    for attempt in range(3):
        try:
            r = _safe_get(url, params=params, headers=headers, timeout=DEFAULT_TIMEOUT)
            if r.status_code == 429:
                import time as _t

                _t.sleep(2**attempt)
                continue
            r.raise_for_status()
            data = r.json()
            break
        except Exception as e:
            last_err = e
    else:
        return [_err("semanticscholar", last_err or Exception("retries exhausted"))]

    out = []
    for p in data.get("data", []):
        out.append(
            _record(
                "semanticscholar",
                title=p.get("title", ""),
                abstract=p.get("abstract") or "",
                url=p.get("url", ""),
                pdf_url=(p.get("openAccessPdf") or {}).get("url", "") or "",
                authors=[a.get("name", "") for a in p.get("authors", []) or []],
                year=p.get("year"),
                doi=(p.get("externalIds") or {}).get("DOI", ""),
            )
        )
    return out


def search_europepmc(query: str, limit: int = DEFAULT_LIMIT) -> List[Dict]:
    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    params = {"query": query, "format": "json", "pageSize": limit, "resultType": "core"}
    try:
        r = _session().get(url, params=params, timeout=DEFAULT_TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return [_err("europepmc", e)]

    out = []
    for p in (data.get("resultList") or {}).get("result", []) or []:
        authors = [
            a.get("fullName", "") for a in (p.get("authorList") or {}).get("author", []) or []
        ]
        full_text_urls = (p.get("fullTextUrlList") or {}).get("fullTextUrl", []) or []
        pdf = next(
            (f.get("url", "") for f in full_text_urls if f.get("documentStyle") == "pdf"), ""
        )
        out.append(
            _record(
                "europepmc",
                title=p.get("title", ""),
                abstract=p.get("abstractText") or "",
                url=(full_text_urls[0].get("url") if full_text_urls else "") or "",
                pdf_url=pdf,
                authors=authors,
                year=int(p["pubYear"]) if p.get("pubYear", "").isdigit() else None,
                doi=p.get("doi", ""),
            )
        )
    return out


def search_pubmed(query: str, limit: int = DEFAULT_LIMIT) -> List[Dict]:
    """NCBI E-utilities — esearch then esummary. Free, no key needed."""
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    try:
        r1 = _session().get(
            f"{base}/esearch.fcgi",
            params={"db": "pubmed", "term": query, "retmax": limit, "retmode": "json"},
            timeout=DEFAULT_TIMEOUT,
        )
        r1.raise_for_status()
        ids = r1.json().get("esearchresult", {}).get("idlist", [])
        if not ids:
            return []
        r2 = _session().get(
            f"{base}/esummary.fcgi",
            params={"db": "pubmed", "id": ",".join(ids), "retmode": "json"},
            timeout=DEFAULT_TIMEOUT,
        )
        r2.raise_for_status()
        summary = r2.json().get("result", {})
    except Exception as e:
        return [_err("pubmed", e)]

    out = []
    for pid in ids:
        rec = summary.get(pid)
        if not rec:
            continue
        authors = [a.get("name", "") for a in rec.get("authors", []) or []]
        doi = next(
            (
                aid.get("value", "")
                for aid in rec.get("articleids", [])
                if aid.get("idtype") == "doi"
            ),
            "",
        )
        year = None
        m = re.search(r"\d{4}", rec.get("pubdate", ""))
        if m:
            year = int(m.group())
        out.append(
            _record(
                "pubmed",
                title=rec.get("title", ""),
                abstract="",
                url=f"https://pubmed.ncbi.nlm.nih.gov/{pid}/",
                authors=authors,
                year=year,
                doi=doi,
            )
        )
    return out


def search_doaj(query: str, limit: int = DEFAULT_LIMIT) -> List[Dict]:
    url = f"https://doaj.org/api/search/articles/{urllib.parse.quote(query)}"
    params = {"pageSize": limit}
    try:
        r = _safe_get(
            url,
            params=params,
            timeout=DEFAULT_TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return [_err("doaj", e)]

    out = []
    for it in data.get("results", []):
        bib = it.get("bibjson", {})
        ids = {x.get("type"): x.get("id") for x in bib.get("identifier", []) or []}
        link = next(
            (l.get("url") for l in bib.get("link", []) or [] if l.get("type") == "fulltext"), ""
        )
        authors = [a.get("name", "") for a in bib.get("author", []) or []]
        out.append(
            _record(
                "doaj",
                title=bib.get("title", ""),
                abstract=bib.get("abstract", ""),
                url=link,
                authors=authors,
                year=int(bib["year"]) if str(bib.get("year", "")).isdigit() else None,
                doi=ids.get("doi", ""),
            )
        )
    return out


def search_dblp(query: str, limit: int = DEFAULT_LIMIT) -> List[Dict]:
    url = "https://dblp.org/search/publ/api"
    params = {"q": query, "format": "json", "h": limit}
    try:
        r = _session().get(url, params=params, timeout=DEFAULT_TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return [_err("dblp", e)]

    out = []
    hits = ((data.get("result") or {}).get("hits") or {}).get("hit") or []
    for h in hits:
        info = h.get("info", {})
        a = info.get("authors", {}).get("author", [])
        if isinstance(a, dict):
            a = [a]
        authors = [x.get("text", "") if isinstance(x, dict) else str(x) for x in a]
        out.append(
            _record(
                "dblp",
                title=info.get("title", ""),
                url=info.get("ee") or info.get("url", ""),
                authors=authors,
                year=int(info["year"]) if str(info.get("year", "")).isdigit() else None,
                doi=info.get("doi", ""),
            )
        )
    return out


def search_openaire(query: str, limit: int = DEFAULT_LIMIT) -> List[Dict]:
    """OpenAIRE Graph API (publicly accessible, no key for basic search)."""
    url = "https://api.openaire.eu/search/publications"
    params = {"title": query, "size": limit, "format": "json"}
    try:
        r = _session().get(url, params=params, timeout=DEFAULT_TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return [_err("openaire", e)]

    out = []
    results = ((data.get("response") or {}).get("results") or {}).get("result") or []
    for it in results:
        try:
            md = it["metadata"]["oaf:entity"]["oaf:result"]
        except (KeyError, TypeError):
            continue
        title = md.get("title")
        if isinstance(title, list):
            title = title[0] if title else ""
        if isinstance(title, dict):
            title = title.get("$", "")
        desc = md.get("description")
        if isinstance(desc, list):
            desc = desc[0] if desc else ""
        if isinstance(desc, dict):
            desc = desc.get("$", "")
        creators = md.get("creator") or []
        if isinstance(creators, dict):
            creators = [creators]
        authors = [c.get("$", "") if isinstance(c, dict) else str(c) for c in creators]
        pid_block = md.get("pid") or []
        if isinstance(pid_block, dict):
            pid_block = [pid_block]
        doi = ""
        for p in pid_block:
            if isinstance(p, dict) and p.get("@classid") == "doi":
                doi = p.get("$", "")
                break
        out.append(
            _record(
                "openaire",
                title=str(title or ""),
                abstract=str(desc or ""),
                url=f"https://doi.org/{doi}" if doi else "",
                authors=authors,
                doi=doi,
            )
        )
    return out


def search_hal(query: str, limit: int = DEFAULT_LIMIT) -> List[Dict]:
    url = "https://api.archives-ouvertes.fr/search/"
    params = {
        "q": query,
        "rows": limit,
        "fl": "title_s,abstract_s,authFullName_s,producedDateY_i,doiId_s,uri_s,fileMain_s",
        "wt": "json",
    }
    try:
        r = _session().get(url, params=params, timeout=DEFAULT_TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return [_err("hal", e)]

    out = []
    for d in (data.get("response") or {}).get("docs") or []:
        title = d.get("title_s")
        if isinstance(title, list):
            title = title[0] if title else ""
        abstract = d.get("abstract_s")
        if isinstance(abstract, list):
            abstract = abstract[0] if abstract else ""
        out.append(
            _record(
                "hal",
                title=title or "",
                abstract=abstract or "",
                url=d.get("uri_s", ""),
                pdf_url=d.get("fileMain_s", "") or "",
                authors=d.get("authFullName_s") or [],
                year=d.get("producedDateY_i"),
                doi=d.get("doiId_s", "") or "",
            )
        )
    return out


def search_plos(query: str, limit: int = DEFAULT_LIMIT) -> List[Dict]:
    url = "https://api.plos.org/search"
    params = {
        "q": query,
        "rows": limit,
        "wt": "json",
        "fl": "id,title,abstract,author,publication_date,journal",
    }
    try:
        r = _session().get(url, params=params, timeout=DEFAULT_TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return [_err("plos", e)]

    out = []
    for d in (data.get("response") or {}).get("docs") or []:
        doi = d.get("id", "")
        abstract = d.get("abstract", "")
        if isinstance(abstract, list):
            abstract = " ".join(abstract)
        title = d.get("title", "")
        if isinstance(title, list):
            title = title[0] if title else ""
        pub = d.get("publication_date", "")
        year = int(pub[:4]) if pub[:4].isdigit() else None
        out.append(
            _record(
                "plos",
                title=title,
                abstract=abstract,
                url=f"https://doi.org/{doi}" if doi else "",
                authors=d.get("author", []) or [],
                year=year,
                doi=doi,
            )
        )
    return out


def search_biorxiv(query: str, limit: int = DEFAULT_LIMIT) -> List[Dict]:
    """bioRxiv/medRxiv don't expose keyword search; we fall back to Europe PMC's
    SRC:PPR filter which indexes both preprint servers."""
    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    params = {
        "query": f"({query}) AND (SRC:PPR)",
        "format": "json",
        "pageSize": limit,
        "resultType": "core",
    }
    try:
        r = _session().get(url, params=params, timeout=DEFAULT_TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return [_err("biorxiv", e)]

    out = []
    for p in (data.get("resultList") or {}).get("result", []) or []:
        out.append(
            _record(
                "biorxiv",
                title=p.get("title", ""),
                abstract=p.get("abstractText") or "",
                url=p.get("doi") and f"https://doi.org/{p['doi']}" or "",
                authors=[
                    a.get("fullName", "")
                    for a in (p.get("authorList") or {}).get("author", []) or []
                ],
                year=int(p["pubYear"]) if p.get("pubYear", "").isdigit() else None,
                doi=p.get("doi", ""),
            )
        )
    return out


def search_fatcat(query: str, limit: int = DEFAULT_LIMIT) -> List[Dict]:
    """Internet Archive Scholar — bot-blocked on the public JSON endpoint
    (returns 405 even with browser UA). Frontend at scholar.archive.org/search
    works in a browser; for programmatic access bridge via OpenAlex DOIs and
    fetch IA snapshots through the Wayback CDX API."""
    return [
        {
            "source": "fatcat",
            "error": "scholar.archive.org JSON API returns 405 to scripts (frontend-only). Use Wayback CDX or OpenAlex bridge.",
        }
    ]


def search_zenodo(query: str, limit: int = DEFAULT_LIMIT) -> List[Dict]:
    url = "https://zenodo.org/api/records"
    params = {"q": query, "size": limit, "type": "publication"}
    try:
        r = _session().get(url, params=params, timeout=DEFAULT_TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return [_err("zenodo", e)]

    out = []
    for h in (data.get("hits") or {}).get("hits") or []:
        meta = h.get("metadata", {})
        creators = meta.get("creators", []) or []
        files = h.get("files", []) or []
        pdf = next((f.get("links", {}).get("self") for f in files if f.get("type") == "pdf"), "")
        pub = meta.get("publication_date", "")
        year = int(pub[:4]) if pub[:4].isdigit() else None
        out.append(
            _record(
                "zenodo",
                title=meta.get("title", ""),
                abstract=re.sub(r"<[^>]+>", "", meta.get("description") or "").strip(),
                url=h.get("links", {}).get("self_html", ""),
                pdf_url=pdf,
                authors=[c.get("name", "") for c in creators],
                year=year,
                doi=meta.get("doi", ""),
            )
        )
    return out


def search_datacite(query: str, limit: int = DEFAULT_LIMIT) -> List[Dict]:
    url = "https://api.datacite.org/dois"
    params = {"query": query, "page[size]": limit}
    try:
        r = _session().get(url, params=params, timeout=DEFAULT_TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return [_err("datacite", e)]

    out = []
    for it in data.get("data", []) or []:
        attr = it.get("attributes", {})
        titles = attr.get("titles") or [{}]
        descs = attr.get("descriptions") or [{}]
        out.append(
            _record(
                "datacite",
                title=titles[0].get("title", "") if titles else "",
                abstract=descs[0].get("description", "") if descs else "",
                url=attr.get("url", ""),
                authors=[c.get("name", "") for c in attr.get("creators", []) or []],
                year=attr.get("publicationYear"),
                doi=attr.get("doi", ""),
            )
        )
    return out


def search_osf(query: str, limit: int = DEFAULT_LIMIT) -> List[Dict]:
    """Open Science Framework — preprints. The compound filter syntax silently
    returns 0 hits, so we filter on title only (most reliable single field)."""
    url = "https://api.osf.io/v2/preprints/"
    params = {"filter[title]": query, "page[size]": limit}
    try:
        r = _session().get(url, params=params, timeout=DEFAULT_TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return [_err("osf", e)]

    out = []
    for it in data.get("data", []) or []:
        a = it.get("attributes", {})
        pub = a.get("date_published") or ""
        year = int(pub[:4]) if pub[:4].isdigit() else None
        out.append(
            _record(
                "osf",
                title=a.get("title", ""),
                abstract=a.get("description", ""),
                url=(it.get("links") or {}).get("html") or "",
                year=year,
                doi=a.get("doi", "") or "",
            )
        )
    return out


def search_paperswithcode(query: str, limit: int = DEFAULT_LIMIT) -> List[Dict]:
    """paperswithcode.com was acquired and now redirects to HuggingFace papers.
    The HF papers search API is the spiritual replacement and exposes the same
    code-linked ML papers."""
    return search_huggingface(query, limit)


def search_huggingface(query: str, limit: int = DEFAULT_LIMIT) -> List[Dict]:
    """HuggingFace papers — undocumented but stable JSON endpoint."""
    url = "https://huggingface.co/api/papers/search"
    params = {"q": query}
    try:
        r = _session().get(url, params=params, timeout=DEFAULT_TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return [_err("huggingface", e)]

    out = []
    for entry in (data or [])[:limit]:
        p = entry.get("paper", {}) if isinstance(entry, dict) else {}
        arxiv_id = p.get("id", "")
        pub = p.get("publishedAt") or ""
        year = int(pub[:4]) if pub[:4].isdigit() else None
        out.append(
            _record(
                "huggingface",
                title=p.get("title", ""),
                abstract=p.get("summary", ""),
                url=f"https://huggingface.co/papers/{arxiv_id}" if arxiv_id else "",
                pdf_url=f"https://arxiv.org/pdf/{arxiv_id}" if arxiv_id else "",
                authors=[a.get("name", "") for a in p.get("authors", []) or []],
                year=year,
            )
        )
    return out


def search_inspirehep(query: str, limit: int = DEFAULT_LIMIT) -> List[Dict]:
    """High-energy physics. Free JSON API."""
    url = "https://inspirehep.net/api/literature"
    params: Dict[str, Any] = {
        "q": query,
        "size": limit,
        "fields": "titles,abstracts,authors,publication_info,arxiv_eprints,dois",
    }
    try:
        r = _session().get(url, params=params, timeout=DEFAULT_TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return [_err("inspirehep", e)]

    out = []
    for h in (data.get("hits") or {}).get("hits") or []:
        m = h.get("metadata", {})
        title = (m.get("titles") or [{}])[0].get("title", "")
        abstract = (m.get("abstracts") or [{}])[0].get("value", "")
        authors = [a.get("full_name", "") for a in m.get("authors", []) or []]
        dois = m.get("dois") or []
        doi = dois[0].get("value", "") if dois else ""
        arxiv = (m.get("arxiv_eprints") or [{}])[0].get("value", "")
        year = (m.get("publication_info") or [{}])[0].get("year")
        out.append(
            _record(
                "inspirehep",
                title=title,
                abstract=abstract,
                url=(
                    f"https://arxiv.org/abs/{arxiv}"
                    if arxiv
                    else (f"https://doi.org/{doi}" if doi else "")
                ),
                authors=authors,
                year=year,
                doi=doi,
            )
        )
    return out


def search_eric(query: str, limit: int = DEFAULT_LIMIT) -> List[Dict]:
    """ERIC — Education Resources Information Center (US Dept. of Education)."""
    url = "https://api.ies.ed.gov/eric/"
    params: Dict[str, Any] = {
        "search": query,
        "format": "json",
        "rows": limit,
        "fields": "title,description,author,publicationdateyear,id,url",
    }
    try:
        r = _session().get(url, params=params, timeout=DEFAULT_TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return [_err("eric", e)]

    out = []
    docs = ((data.get("response") or {}).get("docs")) or []
    for d in docs:
        out.append(
            _record(
                "eric",
                title=d.get("title", ""),
                abstract=(
                    " ".join(d.get("description") or [])
                    if isinstance(d.get("description"), list)
                    else (d.get("description") or "")
                ),
                url=d.get("url", "") or f"https://eric.ed.gov/?id={d.get('id', '')}",
                authors=d.get("author") or [],
                year=d.get("publicationdateyear"),
            )
        )
    return out


# ──────────────────────────────────────────────────────────────────────────
# TIER 2 — KEY REQUIRED (graceful skip if env var is empty)
# ──────────────────────────────────────────────────────────────────────────


def search_core(query: str, limit: int = DEFAULT_LIMIT) -> List[Dict]:
    if not CORE_API_KEY:
        return [
            {
                "source": "core",
                "error": "CORE_API_KEY not set (free key at core.ac.uk/services/api)",
            }
        ]
    url = "https://api.core.ac.uk/v3/search/works"
    headers = {"Authorization": f"Bearer {CORE_API_KEY}", "User-Agent": USER_AGENT}
    params = {"q": query, "limit": limit}
    try:
        r = _safe_get(url, params=params, headers=headers, timeout=DEFAULT_TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return [_err("core", e)]

    out = []
    for p in data.get("results", []) or []:
        ftu = p.get("sourceFulltextUrls") or []
        out.append(
            _record(
                "core",
                title=p.get("title", ""),
                abstract=p.get("abstract") or "",
                url=p.get("downloadUrl") or (ftu[0] if ftu else ""),
                pdf_url=p.get("downloadUrl", "") or "",
                authors=[a.get("name", "") for a in (p.get("authors") or [])],
                year=p.get("yearPublished"),
                doi=p.get("doi", "") or "",
            )
        )
    return out


def search_lens(query: str, limit: int = DEFAULT_LIMIT) -> List[Dict]:
    if not LENS_TOKEN:
        return [{"source": "lens", "error": "LENS_TOKEN not set (free trial token at lens.org)"}]
    url = "https://api.lens.org/scholarly/search"
    headers = {"Authorization": f"Bearer {LENS_TOKEN}", "Content-Type": "application/json"}
    body = {"query": {"match": {"title": query}}, "size": limit}
    try:
        r = _safe_post(url, headers=headers, json=body, timeout=DEFAULT_TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return [_err("lens", e)]

    out = []
    for p in data.get("data", []) or []:
        ext = {e.get("type"): e.get("value") for e in (p.get("external_ids") or [])}
        out.append(
            _record(
                "lens",
                title=p.get("title", ""),
                abstract=p.get("abstract", ""),
                url=(p.get("source_urls") or [""])[0],
                authors=[a.get("display_name", "") for a in (p.get("authors") or [])],
                year=p.get("year_published"),
                doi=ext.get("doi", ""),
            )
        )
    return out


def search_nasa_ads(query: str, limit: int = DEFAULT_LIMIT) -> List[Dict]:
    if not NASA_ADS_TOKEN:
        return [
            {
                "source": "nasa_ads",
                "error": "NASA_ADS_TOKEN not set (free key at ui.adsabs.harvard.edu)",
            }
        ]
    url = "https://api.adsabs.harvard.edu/v1/search/query"
    headers = {"Authorization": f"Bearer {NASA_ADS_TOKEN}"}
    params = {"q": query, "rows": limit, "fl": "title,abstract,author,year,doi,bibcode"}
    try:
        r = _safe_get(url, params=params, headers=headers, timeout=DEFAULT_TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return [_err("nasa_ads", e)]

    out = []
    for d in (data.get("response") or {}).get("docs") or []:
        title = d.get("title", "")
        if isinstance(title, list):
            title = title[0] if title else ""
        out.append(
            _record(
                "nasa_ads",
                title=title,
                abstract=d.get("abstract", ""),
                url=f"https://ui.adsabs.harvard.edu/abs/{d.get('bibcode', '')}",
                authors=d.get("author", []) or [],
                year=d.get("year"),
                doi=(
                    (d.get("doi") or [""])[0]
                    if isinstance(d.get("doi"), list)
                    else d.get("doi", "")
                ),
            )
        )
    return out


def search_springer(query: str, limit: int = DEFAULT_LIMIT) -> List[Dict]:
    if not SPRINGER_KEY:
        return [
            {
                "source": "springer",
                "error": "SPRINGER_API_KEY not set (free at dev.springernature.com)",
            }
        ]
    url = "https://api.springernature.com/meta/v2/json"
    params = {"q": query, "p": limit, "api_key": SPRINGER_KEY}
    try:
        r = _safe_get(url, params=params, timeout=DEFAULT_TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return [_err("springer", e)]

    out = []
    for rec in data.get("records", []) or []:
        out.append(
            _record(
                "springer",
                title=rec.get("title", ""),
                abstract=rec.get("abstract", ""),
                url=rec.get("url", [{}])[0].get("value", "") if rec.get("url") else "",
                authors=[c.get("creator", "") for c in rec.get("creators", [])],
                year=(
                    int((rec.get("publicationDate") or "")[:4])
                    if (rec.get("publicationDate") or "")[:4].isdigit()
                    else None
                ),
                doi=rec.get("doi", ""),
            )
        )
    return out


def search_unpaywall(query: str, limit: int = DEFAULT_LIMIT) -> List[Dict]:
    """Unpaywall: search by query — returns OA versions of articles."""
    if not UNPAYWALL_EMAIL:
        return [
            {
                "source": "unpaywall",
                "error": "UNPAYWALL_EMAIL not set (any email works at unpaywall.org)",
            }
        ]
    url = "https://api.unpaywall.org/v2/search"
    params = {"query": query, "email": UNPAYWALL_EMAIL}
    try:
        r = _safe_get(url, params=params, timeout=DEFAULT_TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return [_err("unpaywall", e)]

    out = []
    for h in (data.get("results") or [])[:limit]:
        r0 = h.get("response", {})
        oa = r0.get("best_oa_location") or {}
        out.append(
            _record(
                "unpaywall",
                title=r0.get("title", ""),
                url=r0.get("doi_url", "") or oa.get("url", ""),
                pdf_url=oa.get("url_for_pdf", "") or "",
                authors=[
                    f"{a.get('given', '')} {a.get('family', '')}".strip()
                    for a in r0.get("z_authors", []) or []
                ],
                year=r0.get("year"),
                doi=r0.get("doi", ""),
            )
        )
    return out


# ──────────────────────────────────────────────────────────────────────────
# Registry & dispatch
# ──────────────────────────────────────────────────────────────────────────

FREE_NO_KEY: Dict[str, Callable] = {
    "openalex": search_openalex,
    "crossref": search_crossref,
    "arxiv": search_arxiv,
    "semanticscholar": search_semantic_scholar,
    "europepmc": search_europepmc,
    "pubmed": search_pubmed,
    "doaj": search_doaj,
    "dblp": search_dblp,
    "openaire": search_openaire,
    "hal": search_hal,
    "plos": search_plos,
    "biorxiv": search_biorxiv,
    "fatcat": search_fatcat,
    "zenodo": search_zenodo,
    "datacite": search_datacite,
    "osf": search_osf,
    "paperswithcode": search_paperswithcode,
    "huggingface": search_huggingface,
    "inspirehep": search_inspirehep,
    "eric": search_eric,
}

KEYED: Dict[str, Callable] = {
    "core": search_core,
    "lens": search_lens,
    "nasa_ads": search_nasa_ads,
    "springer": search_springer,
    "unpaywall": search_unpaywall,
}

SOURCES: Dict[str, Callable] = {**FREE_NO_KEY, **KEYED}


def search_all(
    query: str,
    limit_per_source: int = 3,
    sources: Optional[List[str]] = None,
    include_keyed: bool = False,
) -> List[Dict]:
    if sources is None:
        chosen = list(FREE_NO_KEY.keys())
        if include_keyed:
            chosen += list(KEYED.keys())
    else:
        chosen = sources
    out: List[Dict] = []
    for name in chosen:
        fn = SOURCES.get(name)
        if not fn:
            continue
        try:
            out.extend(fn(query, limit_per_source))
        except Exception as e:
            out.append(_err(name, e))
    return out


def fetch_content(url: str, max_chars: int = 20000) -> str:
    if not url:
        return ""
    try:
        r = _safe_get(
            url, timeout=DEFAULT_TIMEOUT, headers={"User-Agent": USER_AGENT}, allow_redirects=True
        )
        r.raise_for_status()
    except Exception as e:
        return f"[fetch error: {e}]"

    ctype = r.headers.get("Content-Type", "").lower()
    if "pdf" in ctype or url.lower().endswith(".pdf"):
        try:
            from io import BytesIO

            from pypdf import PdfReader

            reader = PdfReader(BytesIO(r.content))
            text = "\n".join((p.extract_text() or "") for p in reader.pages)
            return text[:max_chars]
        except ImportError:
            return "[PDF detected but pypdf not installed: pip install pypdf]"
        except Exception as e:
            return f"[PDF parse error: {e}]"

    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
            tag.decompose()
        return re.sub(r"\s+", " ", soup.get_text(" ", strip=True))[:max_chars]
    except ImportError:
        return r.text[:max_chars]


def format_results(results: List[Dict]) -> str:
    if not results:
        return "(no results)"
    lines = []
    for i, r in enumerate(results, 1):
        if "error" in r:
            lines.append(f"[{r.get('source')}] ERROR: {r['error']}")
            continue
        a = r.get("authors") or []
        a_str = (
            (", ".join(a[:3]) + (" et al." if len(a) > 3 else ""))
            if isinstance(a, list)
            else str(a)
        )
        lines.append(
            f"\n[{i}] ({r.get('source')}) {r.get('title') or '(no title)'}"
            f"\n    Authors : {a_str}"
            f"\n    Year    : {r.get('year', '-')}"
            f"\n    DOI     : {r.get('doi') or '-'}"
            f"\n    URL     : {r.get('url') or '-'}"
            f"\n    PDF     : {r.get('pdf_url') or '-'}"
            f"\n    Abstract: {(r.get('abstract') or '(no abstract)')[:400]}"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    import logging
    import sys

    # Configure logging for CLI usage
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    log = logging.getLogger(__name__)

    q = " ".join(sys.argv[1:]) or "robot agv"
    log.info(f"Query: {q}\n" + "=" * 70)
    res = search_all(q, limit_per_source=2, include_keyed=True)
    log.info(format_results(res))
    ok = [r for r in res if "error" not in r]
    log.info(f"\nTotal results: {len(ok)} / {len(res)} entries")
