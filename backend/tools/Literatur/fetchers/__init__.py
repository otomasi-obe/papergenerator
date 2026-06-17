"""SLR fetchers registry.

Each module exposes `search(client, query, limit, filters) -> Iterable[Paper]`.

`SOURCE_TOPICS` maps each source to the topic areas it serves best so the
orchestrator can pick a relevant set per query (e.g. medical query → europepmc,
CS query → arxiv/dblp/ieee). When a query topic is unknown we fall back to the
broad sources (openalex/crossref/semantic_scholar).

Consolidated 2026-06: 9 publisher wrappers (springer, wiley, spie, ssrn,
emerald, oxford, asce, igi_global, jstor) merged into crossref_publishers
(2 HTTP calls instead of 9). 7 dead stubs removed (taylor_francis, proquest,
ebscohost, mcgrawhill, embase, clinicalkey, westlaw).
"""

from . import (
    arxiv,
    cambridge,
    core,
    crossref,
    crossref_publishers,
    datacite,
    dblp,
    dimensions,
    doaj,
    europepmc,
    hal,
    ieee,
    lens,
    openaire,
    openalex,
    plos,
    pubmed,
    sciencedirect,
    scopus,
    semantic_scholar,
    sinta,
    zenodo,
)

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
    # Crossref publisher batch (8 publishers + SSRN in 2 calls)
    "crossref_publishers": crossref_publishers,
    # Cambridge — HTML scrape
    "cambridge": cambridge,
}

# Each source's strength. Used by orchestrator.pick_sources_for_topic.
# crossref_publishers covers ALL topics since it aggregates 9 publishers.
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
    # Crossref publisher batch — covers all topics (springer+wiley+spie+
    # emerald+oxford+asce+igi+jstor+ssrn)
    "crossref_publishers": {"general", "any", "cs", "ai", "engineering", "medical",
                            "economics", "law", "business", "social", "physics",
                            "education", "biology"},
    # Scrape
    "cambridge": {"general"},
}
