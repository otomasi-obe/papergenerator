"""CLI pipeline SLR end-to-end (gratis, tanpa API berbayar).

Contoh:
    python -m SLR.run_slr "deep learning autonomous driving" \
        --total 200 --top 50 --out results/slr.json

    python -m SLR.run_slr "graph neural network" \
        --sources openalex,crossref,arxiv --per-source 60 --total 300

Output JSON:
    {
      query, generated_at, stats,
      papers: [...],   # SEMUA hasil scrap (dedup-ed)
      top50: [...],    # 50 paper rekomendasi terbaik
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
    print(f"MUST READ        : {s['must_read_count']}")
    print(f"RELEVANT (sbert) : {s['is_relevant_count']}")
    print("=" * 70)

    print("\nPer source:")
    for src, n in sorted(s["papers_by_source"].items(), key=lambda x: -x[1]):
        print(f"  {src:18s} {n:3d}")

    if s["papers_by_year"]:
        print("\nDistribusi tahun (top 10):")
        for y, n in list(s["papers_by_year"].items())[:10]:
            print(f"  {y}: {n}")

    print("\n" + "=" * 70)
    print(f"TOP {min(top_k, len(payload['top50']))} REKOMENDASI:")
    print("=" * 70)
    for i, rec in enumerate(payload["top50"][:10], 1):
        print(f"\n[{i}] {rec['title']}")
        print(f"    score      : {rec['score_total']}  must_read={rec['must_read']}")
        print(f"    source     : {rec['source']}  cit={rec['citations']}")
        venue = rec["publisher_info"].get("venue") or ""
        publisher = rec["publisher_info"].get("publisher") or ""
        year = rec["publisher_info"].get("year") or ""
        print(f"    venue/year : {venue} ({year})  -- {publisher}")
        if rec.get("summary"):
            print(f"    summary    : {rec['summary'][:200]}...")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument(
        "--sources",
        default=",".join(ALL.keys()),
        help=f"Comma-separated dari: {','.join(ALL.keys())}",
    )
    ap.add_argument("--per-source", type=int, default=25)
    ap.add_argument("--total", type=int, default=200, help="Maks total paper unik yang diproses")
    ap.add_argument("--top", type=int, default=50, help="Jumlah paper teratas untuk rekomendasi")
    ap.add_argument("--year-from", type=int, default=None)
    ap.add_argument("--out", default="results/slr.json")
    ap.add_argument("--allow-predatory", action="store_true")
    args = ap.parse_args()

    sources = [s.strip() for s in args.sources.split(",") if s.strip()]
    print(f"Query    : {args.query}")
    print(f"Sources  : {sources}")
    print(f"Per-src  : {args.per_source} | total target unik: {args.total}")
    print(f"Top-K    : {args.top}")
    print(f"Output   : {args.out}\n")

    payload = run(
        query=args.query,
        sources=sources,
        per_source=args.per_source,
        max_total=args.total,
        top_k=args.top,
        year_from=args.year_from,
        skip_predatory=not args.allow_predatory,
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))

    _print_summary(payload, top_k=args.top)
    print(f"\nDisimpan ke: {out_path.resolve()}")


if __name__ == "__main__":
    main()
