"""SLR fetchers registry.

Each module exposes `search(client, query, limit, filters) -> Iterable[Paper]`.

`SOURCE_TOPICS` maps each source to the topic areas it serves best so the
orchestrator can pick a relevant set per query (e.g. medical query → europepmc,
CS query → arxiv/dblp/ieee). When a query topic is unknown we fall back to the
broad sources (openalex/crossref/semantic_scholar).
"""
from . import arxiv, crossref, dblp, europepmc, ieee, openalex, semantic_scholar, sinta

ALL = {
    "openalex": openalex,
    "crossref": crossref,
    "semantic_scholar": semantic_scholar,
    "arxiv": arxiv,
    "dblp": dblp,
    "europepmc": europepmc,
    "ieee": ieee,
    "sinta": sinta,
}

# Each source's strength. Used by orchestrator.pick_sources_for_topic.
# NOTE: orchestrator._detect_topics currently emits only:
#   ai, cs, engineering, medical, indonesia, general
# Other keys below (physics, math, stats, electrical, robotics, biology, health)
# are unused until matching keyword groups are added in orchestrator._TOPIC_KEYWORDS.
SOURCE_TOPICS: dict[str, set[str]] = {
    "openalex":         {"general", "any"},
    "crossref":         {"general", "any"},
    "semantic_scholar": {"general", "cs", "ai", "any"},
    "arxiv":            {"cs", "ai", "physics", "math", "stats"},  # physics/math/stats unused
    "dblp":             {"cs", "ai"},
    "ieee":             {"cs", "ai", "engineering", "electrical", "robotics"},  # electrical/robotics unused
    "europepmc":        {"medical", "biology", "health"},  # biology/health unused
    "sinta":            {"indonesia"},
}
