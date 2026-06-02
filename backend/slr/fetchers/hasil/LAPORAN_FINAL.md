# LAPORAN FINAL TEST SEMUA FETCHER
**Tanggal:** 29 Mei 2026  
**Total Fetcher Ditest:** 26 fetcher  
**Method:** 10 Agent Paralel + Direct Test

---

## 📊 RINGKASAN HASIL

| Kategori | Jumlah | Fetcher |
|----------|--------|---------|
| ✅ **WORKING** (dapat data + link) | **8** | arxiv, crossref, dblp, europepmc, openalex, pubmed, semantic_scholar, sinta |
| 🔑 **PERLU API KEY** | **5** | ieee, sciencedirect, scopus, springer, taylor_francis |
| 🚫 **STUB** (tidak ada public API) | **13** | asce, cambridge, clinicalkey, ebscohost, embase, emerald, igi_global, jstor, mcgrawhill, oxford, proquest, westlaw, wiley |

---

## ✅ FETCHER YANG BEKERJA (8/26)

### 1. ArXiv
- **Keyword:** "deep learning"
- **Papers ditemukan:** 3+
- **Link PDF:** Direct PDF (real, langsung bisa download)
- **Contoh:**
  - `https://arxiv.org/pdf/2306.11113v2.pdf` - "Learn to Accumulate Evidence from All Training Samples"
  - `https://arxiv.org/pdf/2105.04026v2.pdf` - "The Modern Mathematics of Deep Learning"
  - `https://arxiv.org/pdf/2301.00942v1.pdf` - "Deep Learning and Computational Physics"

### 2. CrossRef
- **Keyword:** "machine learning"
- **Papers ditemukan:** 5
- **Link PDF:** DOI links (100% valid)
- **Contoh:**
  - `https://doi.org/10.1093/oso/9780198828044.003.0003` - "Machine learning with sklearn"
  - `https://doi.org/10.1002/9781119902881` - "Optimization and Machine Learning"

### 3. DBLP
- **Keyword:** "database systems"
- **Papers ditemukan:** 5
- **Link PDF:** DOI links (100% valid)
- **Contoh:**
  - `https://doi.org/10.1007/3-540-44472-6` - "Current Issues in Databases and Information Systems"
  - `https://doi.org/10.1007/978-1-4471-3225-7` - "Rules in Database Systems"

### 4. Europe PMC
- **Keyword:** "COVID-19 vaccine"
- **Papers ditemukan:** 5
- **Link PDF:** DOI links (100% valid)
- **Contoh:**
  - `https://doi.org/10.1007/s11606-026-10374-x` - "Correlates of COVID-19 Vaccine Regret"
  - `https://doi.org/10.1097/inf.0000000000005157` - "Evidence for the Effectiveness of COVID-19 Vaccine in Children"
  - `https://doi.org/10.1001/jama.2025.25866` - "COVID-19 Vaccine-Associated Myocarditis"

### 5. OpenAlex
- **Keyword:** "machine learning"
- **Papers ditemukan:** 3+
- **Link PDF:** Direct ArXiv PDF + DOI links
- **Contoh:**
  - `https://arxiv.org/pdf/1201.0490` - "Scikit-learn: Machine Learning in Python"
  - `https://doi.org/10.5860/choice.27-0936` - "Genetic algorithms in search, optimization"
  - `http://lib.myilibrary.com?id=677844` - "C4.5: Programs for Machine Learning"

### 6. PubMed
- **Keyword:** "diabetes"
- **Papers ditemukan:** 3
- **Link PDF:** DOI + PMC links (67% valid, 1 PMC link 404)
- **Contoh:**
  - `https://doi.org/10.1016/j.ecl.2020.05.012` - "Diabetes Insipidus: An Update"
  - `https://doi.org/10.1515/jpem-2021-0566` - "Nephrogenic diabetes insipidus"

### 7. Semantic Scholar
- **Keyword:** "neural networks"
- **Papers ditemukan:** 3+
- **Link PDF:** Direct PDF + DOI links
- **Contoh:**
  - `http://manuscript.elsevier.com/S0021999118307125/pdf/S0021999118307125.pdf` - "Physics-informed neural networks"
  - `https://doi.org/10.1111/J.2517-6161.1992.TB01889.X` - "Finding Chaos in Noisy Systems"
  - `https://www.semanticscholar.org/paper/4f2eda8077dc7a69bb2b4e0a1a086cf054adb3f9` - "EfficientNet"

### 8. SINTA
- **Keyword:** "pendidikan"
- **Papers ditemukan:** 5
- **Link PDF:** Garuda/SINTA links (100% valid, open access)
- **Contoh:**
  - `https://garuda.kemdiktisaintek.go.id/documents/detail/4107696` - "KETERKAITAN ANTARA POLITIK PENDIDIKAN..."
  - `https://garuda.kemdiktisaintek.go.id/documents/detail/5891401` - "Peran Supervisi Pendidikan..."
  - `https://garuda.kemdiktisaintek.go.id/documents/detail/4392411` - "PENDIDIKAN KARAKTER ANAK USIA SEKOLAH DASAR"

---

## 🔑 FETCHER YANG PERLU API KEY (5/26)

| Fetcher | API Key | Cara Dapat |
|---------|---------|------------|
| **IEEE** | `IEEE_API_KEY` | https://developer.ieee.org (gratis) |
| **ScienceDirect** | `ELSEVIER_API_KEY` | https://dev.elsevier.com (gratis) |
| **Scopus** | `ELSEVIER_API_KEY` | https://dev.elsevier.com (gratis) |
| **Springer** | `SPRINGER_API_KEY` | https://dev.springernature.com (gratis) |
| **Taylor & Francis** | `TAYLOR_API_KEY` | Butuh institusional/berbayar |

**Cara setup:**
```bash
export IEEE_API_KEY="your_key"
export ELSEVIER_API_KEY="your_key"
export SPRINGER_API_KEY="your_key"
```

---

## 🚫 FETCHER STUB / TIDAK ADA PUBLIC API (13/26)

Fetcher berikut adalah **intentional stubs** - tidak ada public API yang tersedia:

| Fetcher | Alasan | Alternatif |
|---------|--------|------------|
| ASCE | Tidak ada public API | Gunakan CrossRef/OpenAlex |
| Cambridge | Tidak ada public API | Gunakan CrossRef/OpenAlex |
| ClinicalKey | Butuh institusional | Gunakan PubMed/EuropePMC |
| EBSCOhost | Butuh EBSCO credentials | Gunakan CrossRef/OpenAlex |
| Embase | Butuh Elsevier subscription | Gunakan PubMed/EuropePMC |
| Emerald | Tidak ada public API | Gunakan CrossRef/OpenAlex |
| IGI Global | Tidak ada public API | Gunakan CrossRef/OpenAlex |
| JSTOR | Tidak ada public API | Gunakan CrossRef/OpenAlex |
| McGraw Hill | Tidak ada public API | Gunakan CrossRef/OpenAlex |
| Oxford | Tidak ada public API | Gunakan CrossRef/OpenAlex |
| ProQuest | Butuh institusional | Gunakan CrossRef/OpenAlex |
| Westlaw | Database hukum, bukan akademik | N/A |
| Wiley | Tidak ada public API | Gunakan CrossRef/OpenAlex |

---

## 📈 STATISTIK TOTAL

| Metrik | Nilai |
|--------|-------|
| Total fetcher | 26 |
| Fully working | 8 (31%) |
| Perlu API key | 5 (19%) |
| Stub/tidak bisa | 13 (50%) |
| Total papers retrieved | 34+ |
| Total valid PDF links | 33+ |
| PDF link success rate | ~97% |

---

## 🏆 FETCHER TERBAIK (Rekomendasi)

1. **ArXiv** - Terbaik untuk Computer Science & Physics (free, direct PDF)
2. **OpenAlex** - Terlengkap coverage (multi-domain, free)
3. **Semantic Scholar** - AI-focused papers (free, direct PDF)
4. **Europe PMC** - Terbaik untuk Life Sciences & Medical (free)
5. **CrossRef** - Terluas database (DOI resolver, all domains)
6. **DBLP** - Terbaik untuk Computer Science (free)
7. **PubMed** - Terbaik untuk Medical/Clinical (free, US NIH)
8. **SINTA** - Terbaik untuk penelitian Indonesia (free, Garuda)

---

*Laporan dibuat otomatis oleh 10 agent paralel pada 29 Mei 2026*
