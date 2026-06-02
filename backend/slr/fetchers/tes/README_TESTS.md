# Test Suite untuk Semua Fetchers

## Daftar Test Files

Semua test files berada di `/home/sirobo/papergenerator/backend/slr/fetchers/tes/`

### Fetchers yang TIDAK Memerlukan API Key (Gratis)
1. ✅ **test_arxiv_verified.py** - ArXiv preprints (PDF langsung)
2. ✅ **test_crossref_verified.py** - Crossref metadata (DOI resolver)
3. ✅ **test_dblp_verified.py** - DBLP Computer Science papers
4. ✅ **test_europepmc_verified.py** - Europe PMC biomedical papers
5. ✅ **test_openalex_verified.py** - OpenAlex open database
6. ✅ **test_pubmed_verified.py** - PubMed/MEDLINE biomedical papers
7. ✅ **test_semantic_scholar_verified.py** - Semantic Scholar (rate limit ketat tanpa API key)
8. ✅ **test_sinta_verified.py** - SINTA/Garuda Indonesia papers (scraping HTML)
9. ✅ **test_taylor_francis_verified.py** - Taylor & Francis (skip test - no API)

### Fetchers yang Memerlukan API Key
10. 🔑 **test_ieee_verified.py** - IEEE Xplore (requires `IEEE_API_KEY`)
11. 🔑 **test_scopus_verified.py** - Scopus (requires `ELSEVIER_API_KEY`)
12. 🔑 **test_sciencedirect_verified.py** - ScienceDirect (requires `ELSEVIER_API_KEY`)
13. 🔑 **test_springer_verified.py** - Springer/Nature (requires `SPRINGER_API_KEY`)

## Cara Mendapatkan API Keys (Gratis)

### IEEE API Key
- URL: https://developer.ieee.org
- Gratis, unlimited untuk personal research
- Set environment variable: `export IEEE_API_KEY="your_key_here"`

### Elsevier API Key (untuk Scopus & ScienceDirect)
- URL: https://dev.elsevier.com
- Free tier: 5000 requests/week
- Set environment variable: `export ELSEVIER_API_KEY="your_key_here"`

### Springer API Key
- URL: https://dev.springernature.com
- Free tier dengan rate limits
- Set environment variable: `export SPRINGER_API_KEY="your_key_here"`

### Semantic Scholar API Key (Optional)
- URL: https://www.semanticscholar.org/product/api
- Meningkatkan rate limit dari 1 req/5s ke 10 req/s
- Set environment variable: `export S2_API_KEY="your_key_here"`

## Cara Menjalankan Test

### Test Individual
```bash
cd /home/sirobo/papergenerator/backend/slr/fetchers/tes

# Test fetcher tanpa API key
python test_arxiv_verified.py
python test_crossref_verified.py
python test_dblp_verified.py
python test_openalex_verified.py
python test_pubmed_verified.py
python test_europepmc_verified.py

# Test fetcher dengan API key (jika sudah diset)
python test_ieee_verified.py
python test_scopus_verified.py
python test_springer_verified.py
```

### Test Semua Fetchers Sekaligus
```bash
cd /home/sirobo/papergenerator/backend/slr/fetchers/tes
python run_all_tests.py
```

## Apa yang Diverifikasi

Setiap test memverifikasi:
1. ✅ **Fetcher dapat mengambil data paper** - minimal 3-5 paper
2. ✅ **Paper memiliki metadata lengkap** - title, authors, year, abstract (jika ada)
3. ✅ **Paper memiliki link download REAL** - URL ke PDF atau DOI resolver
4. ✅ **Link download valid** - format URL benar (doi.org, arxiv.org/pdf, dll)

## Format Output Test

Setiap test menampilkan:
```
================================================================================
TESTING [FETCHER NAME] FETCHER
================================================================================

🔍 Query: 'keyword' (limit: 5)
--------------------------------------------------------------------------------

✅ Berhasil mendapatkan 5 paper

📄 Paper 1:
   Title: Paper title here...
   Authors: Author 1, Author 2, Author 3...
   Year: 2024
   DOI: 10.xxxx/xxxxx
   Venue: Journal/Conference Name
   Abstract: Abstract text here...
   📥 Download URL: https://doi.org/10.xxxx/xxxxx
   ✅ VALID LINK (DOI resolver atau PDF)

[... paper 2-5 ...]

================================================================================
HASIL: 5/5 paper memiliki link download
================================================================================
```

## Success Criteria

- **PASS**: ≥80% paper memiliki link download valid
- **FAIL**: <80% paper memiliki link download valid
- **SKIP**: Fetcher di-skip karena tidak ada API key (bukan failure)

## Catatan Penting

### Rate Limits
- **ArXiv**: 10 detik per request (sangat ketat)
- **Semantic Scholar**: 5 detik per request tanpa API key
- **SINTA**: 0.6 detik per request (scraping HTML)
- **Lainnya**: 0.1-0.5 detik per request

### Link Download
- **Direct PDF**: ArXiv, PubMed PMC
- **DOI Resolver**: Crossref, Scopus, IEEE (redirect ke publisher)
- **Landing Page**: DBLP, OpenAlex, Semantic Scholar
- **Publisher Page**: Springer, ScienceDirect, IEEE

### Troubleshooting

**Error: Module not found**
```bash
# Pastikan path benar
cd /home/sirobo/papergenerator/backend/slr/fetchers/tes
python test_arxiv_verified.py
```

**Error: Rate limit exceeded**
- Tunggu beberapa menit
- Untuk Semantic Scholar: set S2_API_KEY
- Untuk ArXiv: sudah ada delay 10 detik built-in

**Error: No papers found**
- Cek koneksi internet
- Coba query yang lebih umum
- Beberapa fetcher mungkin sedang maintenance

## Rekomendasi

1. **Mulai dengan fetchers gratis** - test arxiv, crossref, dblp, openalex dulu
2. **Dapatkan API keys** - IEEE dan Elsevier API gratis untuk research
3. **Run master test** - `python run_all_tests.py` untuk test semua sekaligus
4. **Monitor rate limits** - jangan run test terlalu sering dalam waktu singkat

## Hasil Expected

Dengan setup lengkap (semua API keys), expected results:
- ✅ 9 fetchers PASS (gratis + dengan API key)
- ⚠️ 1 fetcher SKIP (Taylor & Francis - no API)
- Total: 10/10 fetchers berfungsi dengan baik
