import subprocess, collections, re

cmd = ["psql", "-U", "papergenerator", "-d", "papergenerator", "-At", "-F", "\t",
       "-c", "SELECT source, COALESCE(title,''), COALESCE(abstract,'') FROM literature_items WHERE slr_job_id='slr_cc2f716ae0dc';"]

proc = subprocess.run(cmd, capture_output=True, text=True, cwd="/home/sirobo/papergenerator")
lines = proc.stdout.strip().split('\n')

marine = {'marine','sea','ocean','sponge','tunicate','algae','algal','coral','seawater','mangrove','salish','tilapia','aquaculture','fishery','fisheries','kelp','seaweed','coastal','estuary','reef','lagoon','bay','deep-sea','deep sea'}
bio = {'bioactive','compound','compounds','natural product','metabolite','metabolites','secondary metabolite','phenolic','peptide','natural products','bioactivity'}
abx = {'antibiotic','antibacterial','antimicrobial','anti-microbial','resistance','pathogen','biofilm','antifungal','antiviral','bactericidal','bacteriostatic'}

rows = []
for line in lines:
    parts = line.split('\t')
    if len(parts) < 3:
        continue
    src, title, abstract = parts[0], parts[1], parts[2]
    text = (title + ' ' + abstract).lower()
    score = sum(any(x in text for x in group) for group in (marine, bio, abx))
    rows.append((score, src, title))

cnt = collections.Counter(s for s,_,_ in rows)
by_src = collections.defaultdict(collections.Counter)
for s, src, _ in rows:
    by_src[src][s] += 1

print('total', len(rows))
print('score_counts', dict(sorted(cnt.items())))
print('3/3', cnt[3], f'{cnt[3]/len(rows)*100:.1f}%' if rows else '0')
print('2/3+', cnt[2]+cnt[3], f'{(cnt[2]+cnt[3])/len(rows)*100:.1f}%' if rows else '0')

print('\nby_source:')
for src, c in sorted(by_src.items()):
    print(src, dict(sorted(c.items())))

print('\nexamples score3:')
for s, src, title in rows:
    if s == 3:
        print(f'  {src}: {title[:120]}')

print('\nexamples score0 (first 15):')
printed = 0
for s, src, title in rows:
    if s == 0 and printed < 15:
        print(f'  {src}: {title[:120]}')
        printed += 1

print('\nexamples score2 (first 15):')
printed = 0
for s, src, title in rows:
    if s == 2 and printed < 15:
        print(f'  {src}: {title[:120]}')
        printed += 1