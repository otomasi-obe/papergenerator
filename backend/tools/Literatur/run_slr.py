"""CLI Tool Literatur — PostgreSQL scoring → tampil → AI rank → tampil.

Contoh:
    python -m SLR.run_slr "deep learning autonomous driving" --top 50 --out results/slr.json

    python -m SLR.run_slr "graph neural network" --sources openalex,crossref,arxiv --top 30

Output JSON:
    {
      query, generated_at, stats,
      papers: [...],   # SEMUA hasil DB (PG-scored + AI-ranked)
      top_k: [...],    # top-K paper dengan ranking AI
    }
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .fetchers import ALL
from .pipeline import run


def _print_summary(payload: dict, top_k: int) -> None:
    s = payload["stats"]
    print("\n" + "=" * 70)
    print(f"QUERY            : {payload['query']}")
    print(f"GENERATED        : {payload['generated_at']}")
    print(f"TOTAL UNIQUE     : {s['total_unique_papers']}")
    print(f"WITH ABSTRACT    : {s['with_abstract']}")
    print(f"WITH DOI         : {s['with_doi']}")
    print(f"AI RERANKED      : {s.get('ai_reranked', False)}")
    print("=" * 70)

    print("\nPer source:")
    for src, n in sorted(s["papers_by_source"].items(), key=lambda x: -x[1]):
        print(f"  {src:18s} {n:3d}")

    if s["papers_by_year"]:
        print("\nDistribusi tahun (top 10):")
        for y, n in list(s["papers_by_year"].items())[:10]:
            print(f"  {y}: {n}")

    print("\n" + "=" * 70)
    print(f"TOP {min(top_k, len(payload['top_k']))} REKOMENDASI:")
    print("=" * 70)
    for i, rec in enumerate(payload["top_k"][:10], 1):
        print(f"\n[{i}] {rec['title']}")
        db_score = rec.get("db_score")
        rank = rec.get("rank")
        print(f"    db_score   : {db_score}  ai_rank={rank}")
        print(f"    source     : {rec['source']}  cit={rec['citations']}")
        venue = rec.get("venue") or ""
        publisher = rec.get("publisher") or ""
        year = rec.get("year") or ""
        print(f"    venue/year : {venue} ({year})  -- {publisher}")
        abstract = rec.get("abstract") or ""
        if abstract:
            print(f"    abstract   : {abstract[:200]}...")


def main() -> None:
    ap = argparse.ArgumentParser(description="Tool Literatur: PostgreSQL scoring → AI ranking")
    ap.add_argument("query")
    ap.add_argument(
        "--sources",
        default=None,
        help=f"Comma-separated sumber (default: semua): {','.join(ALL.keys())}",
    )
    ap.add_argument("--top", type=int, default=50, help="Jumlah paper teratas (default: 50)")
    ap.add_argument("--year-from", type=int, default=None, help="Filter tahun minimum")
    ap.add_argument("--out", default="results/slr.json", help="Output file path")
    ap.add_argument("--ai-model", default=None, help="AI model untuk rerank (default: primary generate)")
    args = ap.parse_args()

    sources = [s.strip() for s in args.sources.split(",") if s.strip()] if args.sources else None

    print(f"Query    : {args.query}")
    print(f"Sources  : {sources or 'semua'}")
    print(f"Top-K    : {args.top}")
    print(f"Year     : {args.year_from or 'semua'}")
    print(f"Output   : {args.out}\n")

    payload = run(
        query=args.query,
        sources=sources,
        top_k=args.top,
        year_from=args.year_from,
        ai_model=args.ai_model,
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))

    _print_summary(payload, top_k=args.top)
    print(f"\nDisimpan ke: {out_path.resolve()}")


if __name__ == "__main__":
    main()
