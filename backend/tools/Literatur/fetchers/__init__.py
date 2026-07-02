"""SLR fetchers registry.

Each module exposes `search(client, query, limit, filters) -> Iterable[Paper]`.

`SOURCE_TOPICS` maps each source to the topic areas it serves best so the
orchestrator can pick a relevant set per query (e.g. medical query → europepmc,
CS query → arxiv/dblp/ieee). When a query topic is unknown we fall back to the
broad sources (openalex/crossref/semantic_scholar).

Consolidated 2026-06: 9 publisher wrappers (springer, wiley, spie, ssrn,
emerald, oxford, asce, igi_global, jstor) merged into crossref.search_publishers
(2 HTTP calls instead of 9). 5 dead stubs removed (taylor_francis, proquest,
ebscohost, mcgrawhill, westlaw). 2 revived 2026-06: embase + clinicalkey via
Elsevier API.

2026-06 expansion: 10 new fetchers added:
  Paper: unpaywall (OA PDF resolver), opencitations (citation data),
         biorxiv (preprint bio/med), pmc (PubMed Central full-text),
         orcid (author identity/works)
  Books: google_books, open_library, doab (OA books), oapen (OA monographs),
         gutendex (Project Gutenberg)
"""

from . import (
    arxiv,
    biorxiv,
    cambridge,
    clinicalkey,
    core,
    crossref,
    datacite,
    dblp,
    dimensions,
    doab,
    doaj,
    embase,
    europepmc,
    google_books,
    gutendex,
    hal,
    ieee,
    lens,
    open_library,
    openaire,
    openalex,
    opencitations,
    orcid,
    plos,
    pmc,
    pubmed,
    researchgate,
    sciencedirect,
    scopus,
    semantic_scholar,
    sinta,
    unpaywall,
    web,
    wos,
    zenodo,
)
from .oai_pmh import search_oapen
from types import SimpleNamespace

oapen = SimpleNamespace(search=search_oapen)

# crossref_publishers alias — delegates to crossref.search_publishers
crossref_publishers = SimpleNamespace(search=crossref.search_publishers)

ALL = {
    # Free/open sources (no API key required)
    "openalex": openalex,
    "crossref": crossref,
    "semantic_scholar": semantic_scholar,
    "arxiv": arxiv,
    "dblp": dblp,
    "europepmc": europepmc,
    "sinta": sinta,
    "doaj": doaj,
    "plos": plos,
    "openaire": openaire,
    "hal": hal,
    "zenodo": zenodo,
    "datacite": datacite,
    # New paper fetchers (no API key required)
    "unpaywall": unpaywall,
    "opencitations": opencitations,
    "biorxiv": biorxiv,
    "pmc": pmc,
    "orcid": orcid,
    # New book fetchers (no API key required, or free tier keys)
    "google_books": google_books,
    "open_library": open_library,
    "doab": doab,
    "oapen": oapen,
    "gutendex": gutendex,
    # Free with optional API key (higher rate limits)
    "pubmed": pubmed,
    # Requires API key (active when key present)
    "core": core,
    "dimensions": dimensions,
    "lens": lens,
    "scopus": scopus,
    "sciencedirect": sciencedirect,
    # IEEE — keyless internal API
    "ieee": ieee,
    # Crossref publisher batch (8 publishers + SSRN in 2 calls → crossref.search_publishers)
    "crossref_publishers": crossref_publishers,
    # Cambridge — HTML scrape
    "cambridge": cambridge,
    # Elsevier clinical/medical (requires ELSEVIER_API_KEY)
    "embase": embase,
    "clinicalkey": clinicalkey,
    # Web of Science (requires WOS_API_KEY)
    "wos": wos,
    # Web search (DuckDuckGo) — academic paper discovery + landing page scrape
    "web": web,
    # ResearchGate — HTML scrape (no public API, Cloudflare-protected)
    "researchgate": researchgate,
}

# Each source's strength. Used by orchestrator.pick_sources_for_topic.
# crossref_publishers (→ crossref.search_publishers) covers ALL topics since it aggregates 9 publishers.
SOURCE_TOPICS: dict[str, set[str]] = {
    # Broad coverage
    "openalex": {"general", "any"},
    "crossref": {"general", "any"},
    "semantic_scholar": {"general", "cs", "ai", "any"},
    "dimensions": {"general", "any", "economics", "social", "medical"},
    "lens": {"general", "any", "engineering", "agriculture", "economics"},
    # Computer Science & AI
    "arxiv": {"cs", "ai", "physics", "math", "stats"},
    "dblp": {"cs", "ai"},
    "ieee": {"cs", "ai", "engineering", "electrical", "robotics"},
    # Medical & Life Sciences
    "europepmc": {"medical", "biology", "health"},
    "pubmed": {"medical", "biology", "health"},
    "pmc": {"medical", "biology", "health"},
    "biorxiv": {"medical", "biology", "health", "neuroscience"},
    # Publisher-specific
    "core": {"general", "any"},
    "scopus": {"general", "any"},
    "sciencedirect": {"general", "engineering", "medical"},
    # Regional
    "sinta": {"indonesia"},
    # Open access aggregators (keyless)
    "doaj": {"general", "any"},
    "plos": {"medical", "biology", "general"},
    "openaire": {"general", "any", "economics", "social"},
    "hal": {"general", "any", "physics", "cs"},
    "zenodo": {"general", "any"},
    "datacite": {"general", "any"},
    # OA PDF resolvers & citation data
    "unpaywall": {"general", "any"},
    "opencitations": {"general", "any"},
    # Author identity
    "orcid": {"general", "any"},
    # Books (academic + general)
    "google_books": {"general", "any", "humanities", "social"},
    "open_library": {"general", "humanities", "literature"},
    "doab": {"general", "humanities", "social", "economics"},
    "oapen": {"humanities", "social", "economics", "law"},
    "gutendex": {"literature", "humanities", "philosophy"},
    # Crossref publisher batch — covers all topics (→ crossref.search_publishers)
    # springer+wiley+spie+emerald+oxford+asce+igi+jstor+ssrn
    "crossref_publishers": {"general", "any", "cs", "ai", "engineering", "medical",
                            "economics", "law", "business", "social", "physics",
                            "education", "biology"},
    # Scrape
    "cambridge": {"general"},
    # Elsevier clinical/medical
    "embase": {"medical", "biology", "health", "pharmacology"},
    "clinicalkey": {"medical", "health", "clinical", "pharmacology"},
    # Web of Science (multidisciplinary, requires WOS_API_KEY)
    "wos": {"general", "any"},
    # Web search (DuckDuckGo) — covers all topics via landing page scraping
    "web": {"general", "any"},
    # ResearchGate — covers all topics (160M+ publications)
    "researchgate": {"general", "any"},
}