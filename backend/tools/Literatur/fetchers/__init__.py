"""SLR fetchers registry.

Each module exposes `search(client, query, limit, filters) -> Iterable[Paper]`.

`SOURCE_TOPICS` maps each source to the topic areas it serves best so the
orchestrator can pick a relevant set per query (e.g. medical query → europepmc,
CS query → arxiv/dblp/ieee). When a query topic is unknown we fall back to the
broad sources (openalex/crossref/semantic_scholar).
"""

from . import (
    arxiv,
    core,
    crossref,
    dblp,
    dimensions,
    europepmc,
    ieee,
    lens,
    openalex,
    pubmed,
    sciencedirect,
    scopus,
    semantic_scholar,
    sinta,
    springer,
    taylor_francis,
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
    # Free with optional API key (higher rate limits)
    "pubmed": pubmed,
    # Requires API key (free tier available)
    "core": core,
    "dimensions": dimensions,
    "ieee": ieee,
    "lens": lens,
    "scopus": scopus,
    "sciencedirect": sciencedirect,
    "springer": springer,
    # No public API (content available via crossref/openalex)
    "taylor_francis": taylor_francis,
}

# Each source's strength. Used by orchestrator.pick_sources_for_topic.
# NOTE: orchestrator._detect_topics currently emits:
#   ai, cs, engineering, medical, indonesia, biology, physics, economics,
#   social, education, law, agriculture, general
# Other keys below (math, stats, electrical, robotics, health, business)
# are matched via the expanded keyword groups in orchestrator._TOPIC_KEYWORDS.
SOURCE_TOPICS: dict[str, set[str]] = {
    # Broad coverage
    "openalex": {"general", "any"},
    "crossref": {"general", "any"},
    "semantic_scholar": {"general", "cs", "ai", "any"},
    "core": {"general", "any", "social", "education", "law"},
    "dimensions": {"general", "any", "economics", "social", "medical"},
    "lens": {"general", "any", "engineering", "agriculture", "economics"},
    # Computer Science & AI
    "arxiv": {"cs", "ai", "physics", "math", "stats"},
    "dblp": {"cs", "ai"},
    "ieee": {"cs", "ai", "engineering", "electrical", "robotics"},
    "springer": {"cs", "ai", "engineering", "general"},
    # Medical & Life Sciences
    "europepmc": {"medical", "biology", "health"},
    "pubmed": {"medical", "biology", "health"},
    "embase": {"medical", "biology", "health"},
    "clinicalkey": {"medical", "health"},
    # Publisher-specific
    "scopus": {"general", "any"},
    "sciencedirect": {"general", "engineering", "medical"},
    # Regional
    "sinta": {"indonesia"},
    # Stubs (content available via other sources)
    "jstor": {"general"},
    "wiley": {"general"},
    "emerald": {"business", "management"},
    "taylor_francis": {"general"},
    "cambridge": {"general"},
    "oxford": {"general"},
    "asce": {"engineering", "civil"},
    "igi_global": {"cs", "information_science"},
    "proquest": {"general"},
    "ebscohost": {"general"},
}
