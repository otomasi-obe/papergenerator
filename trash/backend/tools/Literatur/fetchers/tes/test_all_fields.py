import sys, os
sys.path.insert(0, os.path.abspath('.'))
sys.path.insert(0, os.path.abspath('tools'))
import importlib
fetchers_mod = importlib.import_module('tools.Literatur.fetchers')
ALL = fetchers_mod.ALL
http_client = importlib.import_module('tools.Literatur.http_client')
get_client = http_client.get_client

QUERY = "machine learning"
LIMIT = 3

def doi_link(p):
    if p.doi:
        return f"https://doi.org/{p.doi}"
    return None

c = get_client()
print(f"QUERY='{QUERY}'  LIMIT={LIMIT}  sources={len(ALL)}\n", flush=True)
hdr = f"{'SOURCE':14} {'n':>2} {'titl':>4} {'abst':>4} {'auth':>4} {'year':>4} {'venue':>5} {'cite':>4} {'doi':>4} {'pdf':>4}"
print(hdr, flush=True); print('-'*len(hdr), flush=True)

summary = {}
for name in sorted(ALL.keys()):
    try:
        papers = list(ALL[name].search(c, QUERY, limit=LIMIT))
    except Exception as e:
        print(f"{name:14} ERROR {type(e).__name__}: {str(e)[:50]}", flush=True)
        summary[name] = "ERR"
        continue
    n = len(papers)
    if n == 0:
        print(f"{name:14} {0:>2}  (empty / stub)", flush=True)
        summary[name] = "empty"
        continue
    def cnt(f):
        return sum(1 for p in papers if f(p))
    t  = cnt(lambda p: bool(p.title))
    ab = cnt(lambda p: bool(p.abstract))
    au = cnt(lambda p: bool(p.authors))
    yr = cnt(lambda p: bool(p.year))
    ve = cnt(lambda p: bool(p.venue) or bool(p.publisher))
    ci = cnt(lambda p: p.citations is not None)
    di = cnt(lambda p: bool(doi_link(p)))
    pd = cnt(lambda p: bool(p.pdf_url))
    print(f"{name:14} {n:>2} {t:>4} {ab:>4} {au:>4} {yr:>4} {ve:>5} {ci:>4} {di:>4} {pd:>4}", flush=True)
    summary[name] = "ok"

print("\n=== SUMMARY ===", flush=True)
ok = [k for k,v in summary.items() if v=='ok']
empty = [k for k,v in summary.items() if v=='empty']
err = [k for k,v in summary.items() if v=='ERR']
print(f"OK ({len(ok)}): {', '.join(ok)}", flush=True)
print(f"EMPTY/STUB ({len(empty)}): {', '.join(empty)}", flush=True)
print(f"ERROR ({len(err)}): {', '.join(err)}", flush=True)
