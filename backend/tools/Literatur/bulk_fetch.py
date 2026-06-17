#!/usr/bin/env python3
"""
Bulk Paper Fetcher v3 — Optimized for throughput.
- Top 6 fastest sources (skip slow/unreliable ones)
- 1 retry only (skip slow topics, move on)
- Streaming save (save per-source, don't wait for all)
- Checkpoint resume

Usage:
    python bulk_fetch.py                    # all topics, 500/topic
    python bulk_fetch.py --topic "X"        # single topic
    python bulk_fetch.py --category food    # single category
    python bulk_fetch.py --no-resume        # ignore checkpoint
"""

import argparse
import json
import os
import sys
import time
import signal
from datetime import datetime
from pathlib import Path

backend_path = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_path))

from tools.Literatur.orchestrator import fetch_titles
from tools.Literatur import db_cache

# Checkpoint
CHECKPOINT_FILE = Path(__file__).parent / ".bulk_fetch_checkpoint.json"

# Top 6 fastest reliable sources (skip slow: cambridge, scopus, sciencedirect,
# sinta, dimensions, lens, crossref_publishers)
FAST_SOURCES = [
    "openalex",           # 200M+ works, fast API
    "semantic_scholar",   # 200M+ papers, good API
    "crossref",           # 150M+ DOIs, reliable
    "arxiv",              # 2.5M preprints, very fast
    "pubmed",             # 36M biomedical, reliable
    "europepmc",          # 43M life sciences, fast
]

# ── Topic matrix: 10 categories × 15 topics = 150 topics ──
TOPIC_MATRIX = {
    "food_engineering": [
        "functional food extraction bioactive compounds antioxidant",
        "food process engineering thermal processing preservation",
        "green extraction technology functional food ingredients",
        "analog rice sweet potato food technology binder formulation",
        "coconut water passion fruit isotonic beverage response surface methodology",
        "ice cream formulation monoglyceride diglyceride emulsifier thermal stability",
        "physicochemical cooking sensory properties analog rice food science",
        "blue pea flower extract flour chemical sensory characteristics",
        "food security national food support sweet potato based",
        "school lunch program challenges Japan Indonesia comparison nutrition",
        "food processing novel technology encapsulation spray drying freeze drying",
        "functional food bioactive peptides antioxidant antimicrobial properties",
        "food packaging biodegradable active intelligent packaging technology",
        "fermentation technology functional food probiotics prebiotics",
        "food waste valorization byproduct utilization circular economy",
    ],
    "esg_finance": [
        "ESG disclosure tax aggressiveness audit quality moderation",
        "green logistics investment financial value creation logistics industry",
        "financial resilience firm performance logistics industry economic uncertainty",
        "sustainability disclosure ESG performance financial value creation logistics firms",
        "corporate governance carbon tax green accounting emission reduction",
        "financial inclusion sustainability development goals greenwashing",
        "ESG green logistics sustainable supply chain management",
        "green finance sustainable investment ESG rating corporate performance",
        "environmental social governance ESG reporting financial performance",
        "sustainable finance taxonomy green bonds impact investing",
        "climate risk financial stability banking sector ESG integration",
        "circular economy business model sustainable finance green innovation",
        "corporate social responsibility ESG firm value emerging markets",
        "green supply chain management financial performance logistics",
        "sustainable development goals SDGs corporate strategy ESG integration",
    ],
    "tax_accounting": [
        "tax compliance costs regulatory complexity corporate compliance",
        "tax incentives sustainability corporate tax behavior",
        "tax avoidance audit quality firm value listed companies",
        "transfer pricing audit committee effectiveness tax avoidance emerging market",
        "financial reporting quality tax compliance UMKM sustainability Indonesia",
        "profitability bank Indonesia credit risk capital efficiency panel data regression",
        "determinant profitability bank Indonesia credit risk capital",
        "integrated reporting sustainability corporate social responsibility",
        "financial reporting quality accounting standards compliance",
        "tax aggressiveness corporate governance audit quality moderation",
        "carbon emission determinants tenure education corporate governance",
        "audit quality earnings management financial statement fraud",
        "tax administration digitalization e-filing e-invoicing compliance",
        "transfer pricing documentation BEPS base erosion profit shifting",
        "forensic accounting fraud detection financial statement analysis",
    ],
    "linguistics": [
        "English medium instruction strengths weaknesses applied foreign language",
        "code switching classroom interaction sociolinguistics multilingual",
        "translanguaging pedagogical practice multilingual classroom",
        "tour guide training task based learning professional communication intercultural",
        "museum storytelling cultural communication local batik museum",
        "risk communication tourism discourse digital tourism dark patterns",
        "digital tourism promotional language post customs free trade port",
        "dark pattern strategies online travel agency platforms linguistic analysis",
        "English language learning acquisition AI integration technology",
        "applied linguistics second language acquisition teaching methodology",
        "critical discourse analysis media communication political discourse",
        "pragmatics cross-cultural communication politeness strategies",
        "corpus linguistics language teaching vocabulary acquisition",
        "academic writing English for specific purposes ESP EAP",
        "language policy bilingual education multilingualism Southeast Asia",
    ],
    "ai_ml": [
        "artificial intelligence renewable energy solar technology optimization",
        "machine learning healthcare applications diagnosis prediction",
        "deep learning computer vision object detection",
        "natural language processing transformers large language models",
        "hyperparameter optimization YOLO model detection accuracy",
        "machine learning multihazard modeling spatial flood vulnerability",
        "artificial intelligence water treatment PLC SCADA automation",
        "AI digital public relations organizational communication",
        "voice AI text AI translanguaging ethical dilemmas",
        "federated learning privacy preserving distributed machine learning",
        "explainable AI interpretability trust machine learning",
        "reinforcement learning robotics autonomous systems control",
        "generative AI diffusion models text to image video generation",
        "AI bias fairness algorithmic accountability ethical AI",
        "edge AI IoT embedded systems real time inference optimization",
    ],
    "engineering": [
        "pavement mechanistic empirical Superpave asphalt optimization",
        "Archimedes screw turbine micro hydropower performance analysis",
        "vertical wind turbine adaptive blade conceptual design",
        "cascade refrigeration system refrigerant selection TOPSIS method",
        "composite materials ballistic performance hybrid multilayered armor",
        "ramie fiber hybrid composites quasi static ballistic impact loading",
        "hardened steel penetration behaviour NIJ level standards",
        "fiber fibrillation banana stem high speed rotation technique",
        "wood powder acacia HDPE hot press mechanical properties",
        "dryer machine solar collector heater solar panel electric modification",
        "building thermal performance passive cooling double skin facade green facade",
        "vertical greenery systems thermal performance systematic literature review",
        "renewable energy smart grid optimization energy storage systems",
        "solar panel hotspot detection convolutional neural networks thermal imaging",
        "solar power forecasting LSTM networks meteorological data",
    ],
    "spatial": [
        "disaster management bibliometric land conversion tropical cyclone Indonesia",
        "tsunami research Aceh bibliometric analysis two decades",
        "green open space monitoring cellular automata geospatial",
        "spatial modeling urban expansion cellular automata artificial neural networks",
        "geospatial automated built-up index urban sprawl monitoring",
        "remote sensing geographic information system spatial planning",
        "spatial accuracy open source geospatial data urban infrastructure planning",
        "water resource management climate change adaptation GIS",
        "biodiversity conservation remote sensing species monitoring",
        "precision agriculture remote sensing crop monitoring yield prediction",
        "urban heat island remote sensing land surface temperature mapping",
        "flood risk mapping GIS multi criteria decision analysis",
        "land use land cover change detection satellite imagery machine learning",
        "sustainable urban development smart city spatial analysis",
        "coastal zone management sea level rise vulnerability assessment GIS",
    ],
    "communication": [
        "digital public relations strategy city branding",
        "AI adoption digital public relations opportunities ethical challenges",
        "ethical challenges artificial intelligence public relations practice",
        "cybersecurity crisis communication organizational reputation",
        "media communication desa wisata model komunikasi Indonesia",
        "media alternatif budaya pinggiran narasi pembentukan subkultur",
        "tindakan komunikasi politik tokoh politik modal sosial akar rumput",
        "creative hub ruang aktualisasi aktivasi dinamika sosial budaya anak muda",
        "media budaya komunikasi politik urban youth subkultur",
        "social media influencer marketing digital communication strategy",
        "political communication social media election campaign disinformation",
        "health communication risk perception behavior change public health",
        "organizational communication digital transformation remote work",
        "intercultural communication globalization cultural identity",
        "journalism studies digital news media literacy fact checking",
    ],
    "islamic_edu": [
        "Islamic religious practices campus mosques habitual formation students",
        "transformation traditional Islamic education Indonesia global Islamic education",
        "mosque metaverse Islamic religious practices simulation theory virtual reality",
        "sustainable development goals SDGs English education integration",
        "Islamic finance Sharia banking financial inclusion developing countries",
        "Islamic education curriculum modernization digital learning",
        "pesantren education character building moral development Indonesia",
        "Islamic philanthropy zakat waqf poverty alleviation social welfare",
        "moderate Islam religious tolerance multicultural education Indonesia",
        "Islamic digital economy fintech halal industry ecosystem",
        "Quranic studies computational linguistics text mining",
        "hadith studies digital authentication methodology",
        "Islamic law maqasid shariah contemporary legal issues",
        "Sufism spirituality mental health wellbeing psychology",
        "Islamic architecture heritage conservation cultural tourism",
    ],
    "archives": [
        "archives management information record family archives assessment",
        "records management practices preservation activities",
        "electronic records retrieval information management",
        "family archives preventive preservation long term archival information",
        "digital archiving metadata standards information retrieval",
        "records management compliance regulatory framework",
        "archival science digital preservation technology blockchain",
        "document management system automation workflow",
        "knowledge management organizational records institutional memory",
        "information governance data lifecycle management privacy",
        "digital curation born digital archives preservation strategies",
        "archival appraisal selection criteria cultural heritage",
        "open data government transparency records access",
        "personal information management digital literacy",
        "cloud computing records management security challenges",
    ],
}


# ── Graceful shutdown ──
_running = True
def _sig_handler(signum, frame):
    global _running
    _running = False
    print(f"\n⏹️  Signal {signum} received, finishing current topic...")

signal.signal(signal.SIGTERM, _sig_handler)
signal.signal(signal.SIGINT, _sig_handler)


def load_checkpoint() -> dict:
    if CHECKPOINT_FILE.exists():
        try:
            return json.loads(CHECKPOINT_FILE.read_text())
        except Exception as _e:
            print(f"[bulk_fetch] Checkpoint file corrupt, starting fresh: {_e}")
    return {"completed": [], "total_fetched": 0}


def save_checkpoint(cp: dict):
    CHECKPOINT_FILE.write_text(json.dumps(cp, indent=2))


def fetch_topic(topic: str, limit: int = 500, year_from: int = 2010) -> int:
    """Fetch papers untuk satu topik. Single attempt, no retry."""
    print(f"\n{'='*70}")
    print(f"📚 {topic[:65]}")
    print(f"{'='*70}")
    start = time.time()

    try:
        papers = fetch_titles(
            query=topic,
            sources=FAST_SOURCES,
            limit_per_source=max(50, limit // len(FAST_SOURCES)),
            filters={"year_from": year_from},
            max_total=limit,
            use_cache=True,
        )
        elapsed = time.time() - start
        count = len(papers)
        print(f"  ✅ {count} papers ({elapsed:.0f}s)")

        if papers:
            try:
                saved = db_cache.save_papers(papers, source="bulk_fetch")
                print(f"  💾 {saved} saved")
            except Exception as e:
                # Partial save fallback
                saved = 0
                for p in papers:
                    try:
                        db_cache.save_papers([p], source="bulk_fetch")
                        saved += 1
                    except Exception as _e:
                        print(f"[bulk_fetch] Partial save failed for paper: {_e}")
                print(f"  💾 {saved}/{count} saved (partial)")
        return count
    except Exception as e:
        elapsed = time.time() - start
        print(f"  ❌ {e} ({elapsed:.0f}s)")
        return 0


def main():
    parser = argparse.ArgumentParser(description="Bulk fetch papers")
    parser.add_argument("--topic", type=str, help="Single topic")
    parser.add_argument("--all-topics", action="store_true", help="All topics")
    parser.add_argument("--category", type=str, help="Category name")
    parser.add_argument("--limit", type=int, default=500, help="Papers/topic (default: 500)")
    parser.add_argument("--year-from", type=int, default=2010, help="Year filter")
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    parser.add_argument("--no-resume", action="store_true", help="Ignore checkpoint")
    parser.add_argument("--sources", type=str, nargs="+", help="Override sources")
    args = parser.parse_args()

    global FAST_SOURCES
    if args.sources:
        FAST_SOURCES = args.sources

    if args.dry_run:
        total = 0
        for cat, topics in TOPIC_MATRIX.items():
            print(f"\n## {cat} ({len(topics)} topics)")
            for t in topics:
                print(f"  - {t}")
            total += len(topics)
        print(f"\nTotal: {total} topics × {args.limit} = {total * args.limit:,} papers")
        print(f"Sources: {FAST_SOURCES}")
        return

    # Build topic list
    if args.topic:
        topics_list = [args.topic]
    elif args.category:
        topics_list = TOPIC_MATRIX.get(args.category, [])
        if not topics_list:
            print(f"❌ Category '{args.category}' not found. Available: {list(TOPIC_MATRIX.keys())}")
            return
    else:
        topics_list = []
        for topics in TOPIC_MATRIX.values():
            topics_list.extend(topics)

    # Resume
    cp = load_checkpoint() if not args.no_resume else {"completed": [], "total_fetched": 0}
    remaining = [t for t in topics_list if t not in cp["completed"]]
    skipped = len(topics_list) - len(remaining)

    print(f"\n🚀 BULK FETCH v3")
    print(f"Sources: {FAST_SOURCES}")
    print(f"Topics: {len(topics_list)} total, {len(remaining)} remaining ({skipped} done)")
    print(f"Target/topic: {args.limit} | Year: {args.year_from}+")
    print(f"Start: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    total_start = time.time()
    total_fetched = cp["total_fetched"]

    for i, topic in enumerate(remaining, 1):
        if not _running:
            print("\n⏹️  Stopped by signal. Checkpoint saved.")
            break

        print(f"\n[{i}/{len(remaining)}] ─────────────")
        count = fetch_topic(topic, args.limit, args.year_from)
        total_fetched += count

        cp["completed"].append(topic)
        cp["total_fetched"] = total_fetched
        cp["last_updated"] = datetime.now().isoformat()
        save_checkpoint(cp)

        # Brief pause
        time.sleep(2)

    elapsed = time.time() - total_start

    print(f"\n{'='*70}")
    print(f"✅ DONE")
    print(f"{'='*70}")
    print(f"Processed: {len(remaining)} topics")
    print(f"Fetched: {total_fetched:,} papers total")
    print(f"Time: {elapsed:.0f}s ({elapsed/60:.1f}m)")

    # DB stats
    try:
        stats = db_cache.get_db_stats()
        print(f"\n📊 DB: {stats.get('total_papers', 0):,} papers | {stats.get('total_sources', 0)} sources | {stats.get('total_jobs', 0)} jobs")
    except Exception as _e:
        print(f"[bulk_fetch] Could not fetch DB stats: {_e}")


if __name__ == "__main__":
    main()
