"""CLI: ambil paper dari multi-source.

Usage:
  python -m SLR.cli "deep learning autonomous driving" --total 50
  python -m SLR.cli "graph neural network" --sources openalex,crossref --total 30
"""

import argparse
import json
from pathlib import Path

from .fetchers import ALL
from .orchestrator import fetch_all


def save_json(papers, path: Path):
    path.write_text(json.dumps([p.to_dict() for p in papers], ensure_ascii=False, indent=2))


def print_report(papers):
    print("\n" + "=" * 70)
    print(f"TOTAL UNIK: {len(papers)}")
    print("=" * 70)
    by_source = {}
    with_abs = 0
    with_doi = 0
    by_year: dict[int, int] = {}
    for p in papers:
        by_source[p.source] = by_source.get(p.source, 0) + 1
        if p.abstract:
            with_abs += 1
        if p.doi:
            with_doi += 1
        if p.year:
            by_year[p.year] = by_year.get(p.year, 0) + 1

    print("\nPer source:")
    for s, n in sorted(by_source.items(), key=lambda x: -x[1]):
        print(f"  {s:18s} {n:3d}")
    print(f"\nDengan abstract: {with_abs}/{len(papers)}")
    print(f"Dengan DOI:      {with_doi}/{len(papers)}")
    if by_year:
        print("\nDistribusi tahun:")
        for y in sorted(by_year, reverse=True)[:10]:
            print(f"  {y}: {by_year[y]}")

    print("\n" + "=" * 70)
    print("SAMPLE 3 PAPER:")
    print("=" * 70)
    for i, p in enumerate(papers[:3], 1):
        print(f"\n[{i}] {p.title}")
        print(f"    sumber : {p.source}")
        print(f"    penulis: {', '.join(p.authors[:5])}{'...' if len(p.authors) > 5 else ''}")
        print(f"    tahun  : {p.year} | venue: {p.venue}")
        print(f"    DOI    : {p.doi}")
        print(f"    sitasi : {p.citations} | OA: {p.is_open_access}")
        if p.abstract:
            abs_short = p.abstract[:240].replace("\n", " ")
            print(f"    abs    : {abs_short}...")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query", help="Query pencarian")
    ap.add_argument(
        "--sources",
        default=",".join(ALL.keys()),
        help=f"Comma-separated. Pilihan: {','.join(ALL.keys())}",
    )
    ap.add_argument("--per-source", type=int, default=20)
    ap.add_argument("--total", type=int, default=50)
    ap.add_argument("--out", default="results")
    ap.add_argument("--year-from", type=int, default=None)
    args = ap.parse_args()

    sources = [s.strip() for s in args.sources.split(",") if s.strip()]
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Query    : {args.query}")
    print(f"Sources  : {sources}")
    print(f"Per-src  : {args.per_source} | Target unik: {args.total}\n")

    papers = fetch_all(
        query=args.query,
        sources=sources,
        limit_per_source=args.per_source,
        max_total=args.total,
    )

    if args.year_from:
        papers = [p for p in papers if p.year and p.year >= args.year_from]

    save_json(papers, out_dir / "papers.json")
    print_report(papers)
    print(f"\nDisimpan ke: {out_dir / 'papers.json'}")


if __name__ == "__main__":
    main()
