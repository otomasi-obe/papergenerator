import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.Literatur.slr import _parse_inline_fetcher_queries


def test_parse_inline_fetcher_queries_multiple_sources():
    plain, fetch_map = _parse_inline_fetcher_queries(
        "robot agv line follower arxiv:robot agv arxiv:line follower scopus:robot agv scholar:robot"
    )

    assert plain == "robot agv line follower"
    assert fetch_map == {
        "arxiv": ["robot agv", "line follower"],
        "scopus": ["robot agv"],
        "semantic_scholar": ["robot"],
    }


def test_parse_inline_fetcher_queries_ignores_unknown_prefix():
    plain, fetch_map = _parse_inline_fetcher_queries("robot topic:agv arxiv:robot")

    assert plain == "robot topic:agv"
    assert fetch_map == {"arxiv": ["robot"]}
