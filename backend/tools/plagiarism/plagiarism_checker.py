import re
import math
import hashlib
import logging
import time
import json
import os
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlparse

log = logging.getLogger(__name__)

_ACADEMIC_DOMAINS = frozenset({
    '.edu', '.ac.uk', '.ac.jp', '.ac.in', '.edu.au', '.edu.cn',
    'scholar.google', 'crossref.org', 'doi.org', 'arxiv.org',
    'researchgate.net', 'semanticscholar.org', 'pubmed.ncbi.nlm.nih.gov',
    'ieee.org', 'acm.org', 'springer.com', 'elsevier.com', 'wiley.com',
    'nature.com', 'science.org', 'jstor.org', 'pnas.org',
})

_LOW_CRED_DOMAINS = frozenset({
    'blogspot', 'wordpress.com', 'medium.com', 'quora.com',
    'answers.yahoo', 'wikihow.com', 'brainly.com', 'chegg.com',
})


class TextPreprocessor:
    _STOPWORDS = frozenset({
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
        'of', 'with', 'by', 'from', 'is', 'are', 'was', 'were', 'be', 'been',
        'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
        'could', 'should', 'may', 'might', 'shall', 'can', 'this', 'that',
        'these', 'those', 'it', 'its', 'i', 'you', 'he', 'she', 'we', 'they',
        'what', 'which', 'who', 'whom', 'when', 'where', 'why', 'how', 'not',
        'no', 'so', 'if', 'then', 'than', 'too', 'very', 'just', 'about',
        'also', 'more', 'other', 'some', 'any', 'each', 'every', 'all', 'both',
        'few', 'most', 'own', 'same', 'such', 'into', 'over', 'after', 'before',
        'between', 'through', 'during', 'above', 'below', 'up', 'down', 'out',
    })

    @staticmethod
    def normalize(text):
        text = text.lower()
        text = re.sub(r'[^\w\s]', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    @staticmethod
    def tokenize(text, n=1):
        words = text.split()
        if n == 1:
            return words
        return [' '.join(words[i:i + n]) for i in range(len(words) - n + 1)]

    @classmethod
    def remove_stopwords(cls, tokens):
        return [t for t in tokens if t.lower() not in cls._STOPWORDS]

    @staticmethod
    def split_sentences(text):
        text = re.sub(r'\s+', ' ', text).strip()
        if not text:
            return []
        parts = re.split(r'(?<=[.!?])\s+|\n+', text)
        return [p.strip() for p in parts if p.strip()]


class NGramFingerprint:
    def __init__(self, k=5, window=4):
        self.k = k
        self.window = window

    def _hash(self, ngram):
        return int(hashlib.md5(ngram.encode()).hexdigest(), 16)

    def fingerprint(self, text):
        normalized = TextPreprocessor.normalize(text)
        tokens = normalized.split()
        if len(tokens) < self.k:
            return set()
        kgrams = [' '.join(tokens[i:i + self.k]) for i in range(len(tokens) - self.k + 1)]
        hashes = [self._hash(kg) for kg in kgrams]
        fps = set()
        for i in range(len(hashes) - self.window + 1):
            fps.add(min(hashes[i:i + self.window]))
        return fps

    def compare(self, text1, text2):
        fp1 = self.fingerprint(text1)
        fp2 = self.fingerprint(text2)
        if not fp1 or not fp2:
            return {"similarity": 0.0, "common_fingerprints": 0}
        common = fp1 & fp2
        union = fp1 | fp2
        return {
            "similarity": round(len(common) / len(union), 4) if union else 0.0,
            "common_fingerprints": len(common),
            "doc1_fingerprints": len(fp1),
            "doc2_fingerprints": len(fp2),
        }


class TFIDFComparator:
    def _compute_tf(self, tokens):
        counts = Counter(tokens)
        total = len(tokens)
        return {t: c / total for t, c in counts.items()} if total else {}

    def _compute_idf(self, docs):
        n = len(docs)
        df = Counter()
        for doc in docs:
            for term in set(doc):
                df[term] += 1
        return {t: math.log(n / (1 + c)) for t, c in df.items()}

    def _cosine(self, v1, v2):
        common = set(v1) & set(v2)
        if not common:
            return 0.0
        dot = sum(v1[t] * v2[t] for t in common)
        m1 = math.sqrt(sum(x ** 2 for x in v1.values()))
        m2 = math.sqrt(sum(x ** 2 for x in v2.values()))
        return round(dot / (m1 * m2), 4) if m1 and m2 else 0.0

    def compare(self, text1, text2):
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.metrics.pairwise import cosine_similarity
            vec = TfidfVectorizer(ngram_range=(1, 3), stop_words='english', max_features=10000)
            tfidf = vec.fit_transform([text1, text2])
            sim = float(cosine_similarity(tfidf[0:1], tfidf[1:2])[0][0])
            return {"similarity": round(sim, 4), "method": "tfidf_cosine_sklearn"}
        except Exception:
            pass
        tokens1 = TextPreprocessor.tokenize(TextPreprocessor.normalize(text1))
        tokens2 = TextPreprocessor.tokenize(TextPreprocessor.normalize(text2))
        idf = self._compute_idf([tokens1, tokens2])
        tf1 = self._compute_tf(tokens1)
        tf2 = self._compute_tf(tokens2)
        v1 = {t: tf1.get(t, 0) * idf.get(t, 0) for t in set(tokens1)}
        v2 = {t: tf2.get(t, 0) * idf.get(t, 0) for t in set(tokens2)}
        return {"similarity": self._cosine(v1, v2), "method": "tfidf_cosine_manual"}


class JaccardComparator:
    @staticmethod
    def compare(text1, text2, n=1):
        s1 = set(TextPreprocessor.tokenize(TextPreprocessor.normalize(text1), n))
        s2 = set(TextPreprocessor.tokenize(TextPreprocessor.normalize(text2), n))
        if not s1 or not s2:
            return {"similarity": 0.0, "method": f"jaccard_{n}gram"}
        inter = s1 & s2
        union = s1 | s2
        return {
            "similarity": round(len(inter) / len(union), 4),
            "method": f"jaccard_{n}gram",
            "intersection_size": len(inter),
            "union_size": len(union),
        }


class LCSComparator:
    @staticmethod
    def _lcs_length(t1, t2):
        m, n = len(t1), len(t2)
        if m == 0 or n == 0:
            return 0
        prev = [0] * (n + 1)
        curr = [0] * (n + 1)
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if t1[i - 1] == t2[j - 1]:
                    curr[j] = prev[j - 1] + 1
                else:
                    curr[j] = max(prev[j], curr[j - 1])
            prev, curr = curr, prev
        return prev[n]

    def compare(self, text1, text2):
        t1 = TextPreprocessor.normalize(text1).split()
        t2 = TextPreprocessor.normalize(text2).split()
        lcs = self._lcs_length(t1, t2)
        m = max(len(t1), len(t2))
        return {
            "similarity": round(lcs / m, 4) if m else 0.0,
            "method": "lcs",
            "lcs_length": lcs,
            "doc1_length": len(t1),
            "doc2_length": len(t2),
        }


class SequenceMatcherComparator:
    @staticmethod
    def ratio(text1, text2):
        return SequenceMatcher(None, text1, text2).ratio()


class WebSearchPlagiarism:
    def __init__(self):
        self._ddgs = None

    def _get_ddgs(self):
        if self._ddgs is None:
            try:
                from ddgs import DDGS
                self._ddgs = DDGS()
            except ImportError:
                try:
                    from duckduckgo_search import DDGS
                    self._ddgs = DDGS()
                except ImportError:
                    raise RuntimeError("duckduckgo-search not installed")
        return self._ddgs

    @staticmethod
    def _domain_credibility(url):
        if not url:
            return "low", "unknown"
        parsed = urlparse(url)
        host = parsed.hostname or ""
        host_lower = host.lower()
        for d in _ACADEMIC_DOMAINS:
            if d in host_lower:
                return "high", "academic"
        for d in _LOW_CRED_DOMAINS:
            if d in host_lower:
                return "low", "web"
        if host_lower.endswith('.gov') or host_lower.endswith('.ac.id'):
            return "high", "academic"
        return "medium", "web"

    def extract_key_phrases(self, text, n_phrases=8, phrase_len=8):
        sentences = TextPreprocessor.split_sentences(text)
        if not sentences:
            words = text.split()
            if len(words) <= phrase_len:
                return [text]
            return [' '.join(words[i:i + phrase_len]) for i in range(0, min(n_phrases, len(words) - phrase_len + 1))]

        scored = []
        word_freq = Counter(TextPreprocessor.normalize(text).split())
        for sent in sentences:
            words = sent.split()
            if len(words) < 4:
                continue
            norm_words = TextPreprocessor.normalize(sent).split()
            content_words = TextPreprocessor.remove_stopwords(norm_words)
            if not content_words:
                continue
            score = sum(word_freq.get(w, 0) for w in content_words) / max(len(content_words), 1)
            length_bonus = min(len(words) / phrase_len, 1.0)
            scored.append((sent, score * length_bonus))

        scored.sort(key=lambda x: x[1], reverse=True)
        phrases = []
        for sent, _ in scored:
            words = sent.split()
            if len(words) <= phrase_len:
                phrases.append(sent)
            else:
                step = max(1, (len(words) - phrase_len) // 2)
                for i in range(0, len(words) - phrase_len + 1, step):
                    phrases.append(' '.join(words[i:i + phrase_len]))
                    if len(phrases) >= n_phrases:
                        break
            if len(phrases) >= n_phrases:
                break
        return phrases[:n_phrases] if phrases else [text[:200]]

    def search_phrase(self, phrase, max_results=5, academic=False):
        ddgs = self._get_ddgs()
        matches = []
        queries = [f'"{phrase}"']
        if academic:
            queries.append(f'"{phrase}" site:scholar.google.com OR site:arxiv.org OR site:researchgate.net OR site:semanticscholar.org')
        for query in queries:
            try:
                results = ddgs.text(query, max_results=max_results, safesearch='off')
                for r in results:
                    snippet = r.get('body', '')
                    if not snippet:
                        continue
                    phrase_lower = phrase.lower()
                    snippet_lower = snippet.lower()
                    if phrase_lower in snippet_lower:
                        match_ratio = SequenceMatcher(None, phrase_lower, snippet_lower).ratio()
                    else:
                        pw = set(TextPreprocessor.normalize(phrase).split())
                        sw = set(TextPreprocessor.normalize(snippet).split())
                        if pw and sw:
                            overlap = len(pw & sw) / len(pw | sw)
                            match_ratio = overlap * 0.8
                        else:
                            match_ratio = 0.0
                    if match_ratio < 0.15:
                        continue
                    cred, src_type = self._domain_credibility(r.get('href', ''))
                    matches.append({
                        'url': r.get('href', ''),
                        'title': r.get('title', ''),
                        'snippet': snippet[:300],
                        'match_ratio': round(match_ratio, 4),
                        'phrase': phrase,
                        'credibility': cred,
                        'source_type': src_type,
                    })
            except Exception as e:
                log.warning("DDGS search failed for query '%s': %s", query[:60], e)
        return matches

    def check(self, text, n_phrases=8, phrase_len=8, include_academic=True):
        phrases = self.extract_key_phrases(text, n_phrases, phrase_len)
        all_matches = []
        for phrase in phrases:
            matches = self.search_phrase(phrase, max_results=5)
            all_matches.extend(matches)
            if include_academic:
                acad_matches = self.search_phrase(phrase, max_results=3, academic=True)
                all_matches.extend(acad_matches)
            time.sleep(1.5)

        if not all_matches:
            return {
                "pct": 0,
                "sources": [],
                "reasons": ["No matching content found online"],
                "suggestions": ["Text appears original based on web search"],
                "highlighted_sentences": [],
                "method": "web_search",
                "breakdown": {"verbatim_pct": 0, "paraphrased_pct": 0, "idea_pct": 0},
            }

        all_matches.sort(key=lambda x: x.get('match_ratio', 0), reverse=True)
        top = all_matches[:15]
        match_pcts = [m['match_ratio'] * 100 for m in top]
        avg_pct = sum(match_pcts) / len(match_pcts) if match_pcts else 0
        high_cred_bonus = sum(5 for m in top if m.get('credibility') == 'high')
        pct = min(round(avg_pct * 1.3 + high_cred_bonus), 100)

        sources = []
        seen_urls = set()
        for m in top:
            url = m['url']
            if url not in seen_urls:
                seen_urls.add(url)
                sources.append({
                    'url': url,
                    'title': m['title'],
                    'match_pct': round(m['match_ratio'] * 100, 1),
                    'credibility': m.get('credibility', 'medium'),
                    'type': m.get('source_type', 'unknown'),
                })

        verbatim_count = sum(1 for m in top if m['match_ratio'] > 0.7)
        paraphrased_count = sum(1 for m in top if 0.4 < m['match_ratio'] <= 0.7)
        idea_count = sum(1 for m in top if m['match_ratio'] <= 0.4)
        vb_pct = min(round(verbatim_count / max(len(top), 1) * 100 * 1.2), 100)
        pp_pct = min(round(paraphrased_count / max(len(top), 1) * 100 * 1.1), 100)
        id_pct = min(round(idea_count / max(len(top), 1) * 100), 100)

        reasons = []
        if verbatim_count > 0:
            reasons.append(f"Found {verbatim_count} verbatim or near-verbatim online matches")
        if paraphrased_count > 0:
            reasons.append(f"Found {paraphrased_count} paraphrased online matches")
        if idea_count > 0:
            reasons.append(f"Found {idea_count} passages with similar ideas online")
        if not reasons:
            reasons.append(f"Found {len(all_matches)} minor online matches")

        sentences = TextPreprocessor.split_sentences(text)
        highlighted = []
        seen_texts = set()
        for m in top[:8]:
            key_text = m['phrase'][:120]
            if key_text in seen_texts:
                continue
            seen_texts.add(key_text)
            ctx_before, ctx_after = "", ""
            for idx, s in enumerate(sentences):
                if m['phrase'].lower() in s.lower() or s.lower() in m['phrase'].lower():
                    ctx_before = sentences[idx - 1][:100] if idx > 0 else ""
                    ctx_after = sentences[idx + 1][:100] if idx + 1 < len(sentences) else ""
                    break
            severity = 'high' if m['match_ratio'] > 0.7 else 'moderate' if m['match_ratio'] > 0.4 else 'low'
            issue = 'verbatim match' if m['match_ratio'] > 0.7 else 'paraphrased content' if m['match_ratio'] > 0.4 else 'similar idea'
            highlighted.append({
                'text': m['phrase'][:200],
                'issue': issue,
                'severity': severity,
                'note': f"Source: {m['title'][:80]} (credibility: {m.get('credibility', 'unknown')})",
                'context_before': ctx_before,
                'context_after': ctx_after,
            })

        return {
            "pct": pct,
            "sources": sources[:10],
            "reasons": reasons,
            "suggestions": [
                "Paraphrase matched passages to improve originality",
                "Add proper citations for referenced material",
                "Use quotation marks for direct quotes with source attribution",
            ],
            "highlighted_sentences": highlighted,
            "method": "web_search",
            "breakdown": {
                "verbatim_pct": vb_pct,
                "paraphrased_pct": pp_pct,
                "idea_pct": id_pct,
            },
        }


class OfflineAnalyzer:
    def __init__(self):
        self.fingerprinter = NGramFingerprint(k=5, window=4)
        self.tfidf = TFIDFComparator()
        self.jaccard = JaccardComparator()
        self.lcs = LCSComparator()

    def _sliding_window_similarity(self, sentences, window=3):
        if len(sentences) < window * 2:
            return []
        chunks = []
        for i in range(0, len(sentences) - window + 1, max(1, window // 2)):
            chunk = ' '.join(sentences[i:i + window])
            if chunk.strip():
                chunks.append((i, chunk))
        pair_scores = []
        for i in range(len(chunks)):
            for j in range(i + 1, len(chunks)):
                idx_i, chunk_i = chunks[i]
                idx_j, chunk_j = chunks[j]
                gap = abs(idx_i - idx_j)
                if gap < window:
                    continue
                sim = self.tfidf.compare(chunk_i, chunk_j)['similarity']
                if sim > 0.3:
                    pair_scores.append({
                        'chunk_a_start': idx_i,
                        'chunk_b_start': idx_j,
                        'similarity': sim,
                        'text_a': chunk_i[:150],
                        'text_b': chunk_j[:150],
                    })
        return pair_scores

    def _ngram_repetition_map(self, text, n=5):
        normalized = TextPreprocessor.normalize(text)
        tokens = normalized.split()
        if len(tokens) < n:
            return {}
        ngram_positions = {}
        for i in range(len(tokens) - n + 1):
            gram = ' '.join(tokens[i:i + n])
            ngram_positions.setdefault(gram, []).append(i)
        repeats = {g: positions for g, positions in ngram_positions.items() if len(positions) > 1}
        return repeats

    def analyze(self, text):
        normalized = TextPreprocessor.normalize(text)
        tokens = normalized.split()
        word_count = len(tokens)

        if word_count < 10:
            return {
                "pct": 0,
                "reasons": ["Text too short for offline analysis"],
                "suggestions": ["Provide more text for accurate analysis"],
                "highlighted_sentences": [],
                "sources": [],
                "method": "offline",
                "details": {},
                "breakdown": {"verbatim_pct": 0, "paraphrased_pct": 0, "idea_pct": 0},
            }

        sentences = TextPreprocessor.split_sentences(text)
        n_sents = len(sentences)

        internal_scores = {}
        if n_sents >= 4:
            chunk_size = max(3, n_sents // 3)
            chunks = []
            for i in range(0, n_sents, chunk_size):
                chunk = ' '.join(sentences[i:i + chunk_size])
                if chunk.strip():
                    chunks.append(chunk)

            pair_scores = []
            for i in range(len(chunks)):
                for j in range(i + 1, len(chunks)):
                    sim = self.tfidf.compare(chunks[i], chunks[j])['similarity']
                    pair_scores.append(sim)
            if pair_scores:
                internal_scores['self_similarity'] = round(sum(pair_scores) / len(pair_scores), 4)

        sliding_dupes = self._sliding_window_similarity(sentences)
        internal_scores['sliding_window_duplicates'] = len(sliding_dupes)
        if sliding_dupes:
            internal_scores['avg_sliding_similarity'] = round(
                sum(d['similarity'] for d in sliding_dupes) / len(sliding_dupes), 4
            )

        repetition_ratio = 0.0
        if word_count >= 50:
            chunk_a = ' '.join(tokens[:word_count // 2])
            chunk_b = ' '.join(tokens[word_count // 2:])
            rep_sim = SequenceMatcher(None, chunk_a, chunk_b).ratio()
            repetition_ratio = round(rep_sim, 4)
            internal_scores['first_half_vs_second_half'] = repetition_ratio

        ngram_repeats = self._ngram_repetition_map(text, n=5)
        long_repeats = {g: p for g, p in ngram_repeats.items() if len(p) >= 3}
        internal_scores['repeated_ngrams_5'] = len(ngram_repeats)
        internal_scores['frequently_repeated_ngrams'] = len(long_repeats)

        internal_scores['unigram_vocab_ratio'] = round(len(set(tokens)) / word_count, 4) if word_count else 0

        sentence_scores = []
        highlighted = []
        if n_sents >= 3:
            for idx, sent in enumerate(sentences):
                if len(sent.split()) < 5:
                    continue
                others = ' '.join(sentences[:idx] + sentences[idx + 1:])
                sm = SequenceMatcher(None, sent.lower(), others.lower())
                ratio = sm.ratio()
                if ratio > 0.5:
                    sentence_scores.append((idx, sent, ratio))
                    ctx_before = sentences[idx - 1][:100] if idx > 0 else ""
                    ctx_after = sentences[idx + 1][:100] if idx + 1 < len(sentences) else ""
                    highlighted.append({
                        'text': sent[:200],
                        'issue': 'High internal repetition detected',
                        'severity': 'high' if ratio > 0.8 else 'moderate' if ratio > 0.6 else 'low',
                        'note': f'Similarity ratio: {ratio:.2f}',
                        'context_before': ctx_before,
                        'context_after': ctx_after,
                    })

        for dup in sliding_dupes[:5]:
            if dup['similarity'] > 0.5:
                highlighted.append({
                    'text': dup['text_a'][:200],
                    'issue': 'Repeated passage in different section',
                    'severity': 'high' if dup['similarity'] > 0.7 else 'moderate',
                    'note': f'Similarity: {dup["similarity"]:.2f} (found at position {dup["chunk_b_start"]})',
                    'context_before': '',
                    'context_after': '',
                })

        vocab_diversity = internal_scores.get('unigram_vocab_ratio', 1.0)
        self_sim = internal_scores.get('self_similarity', 0)
        rep = internal_scores.get('first_half_vs_second_half', 0)
        sliding_count = internal_scores.get('sliding_window_duplicates', 0)
        freq_ngrams = internal_scores.get('frequently_repeated_ngrams', 0)

        pct_raw = 0
        if vocab_diversity < 0.3:
            pct_raw += 25
        elif vocab_diversity < 0.5:
            pct_raw += 15
        elif vocab_diversity < 0.7:
            pct_raw += 5

        if self_sim > 0.7:
            pct_raw += 30
        elif self_sim > 0.5:
            pct_raw += 20
        elif self_sim > 0.3:
            pct_raw += 10

        if rep > 0.6:
            pct_raw += 25
        elif rep > 0.4:
            pct_raw += 15

        if sliding_count > 5:
            pct_raw += 20
        elif sliding_count > 2:
            pct_raw += 10

        if freq_ngrams > 10:
            pct_raw += 15
        elif freq_ngrams > 5:
            pct_raw += 8

        sent_dup_count = len(sentence_scores)
        if sent_dup_count > n_sents * 0.5:
            pct_raw += 20
        elif sent_dup_count > n_sents * 0.3:
            pct_raw += 10

        pct = min(pct_raw, 100)

        reasons = []
        if vocab_diversity < 0.5:
            reasons.append(f"Low vocabulary diversity ({vocab_diversity:.0%})")
        if self_sim > 0.5:
            reasons.append(f"High internal self-similarity ({self_sim:.0%})")
        if rep > 0.4:
            reasons.append(f"Significant content repetition between halves ({rep:.0%})")
        if sliding_count > 2:
            reasons.append(f"{sliding_count} passages repeat across different sections")
        if freq_ngrams > 5:
            reasons.append(f"{freq_ngrams} phrases repeated 3+ times within the text")
        if sent_dup_count > 2:
            reasons.append(f"{sent_dup_count} sentences show high similarity to other parts")
        if not reasons:
            reasons.append("No significant internal patterns detected")

        suggestions = []
        if vocab_diversity < 0.5:
            suggestions.append("Increase vocabulary variety to improve originality")
        if self_sim > 0.5:
            suggestions.append("Reduce repetitive passages across sections")
        if rep > 0.4:
            suggestions.append("Avoid repeating similar content in different paragraphs")
        if sliding_count > 2:
            suggestions.append("Consolidate repeated passages — same ideas appear in multiple sections")
        if freq_ngrams > 5:
            suggestions.append("Vary phrasing for frequently repeated concepts")
        if not suggestions:
            suggestions.append("Text appears structurally diverse and original")

        vb_pct = min(30 if freq_ngrams > 5 else 10 if freq_ngrams > 0 else 0, 100)
        pp_pct = min(40 if sliding_count > 3 else 15 if sliding_count > 0 else 0, 100)
        id_pct = min(20 if self_sim > 0.5 else 5 if self_sim > 0.3 else 0, 100)

        return {
            "pct": pct,
            "reasons": reasons,
            "suggestions": suggestions,
            "highlighted_sentences": highlighted,
            "sources": [],
            "method": "offline",
            "details": internal_scores,
            "breakdown": {
                "verbatim_pct": vb_pct,
                "paraphrased_pct": pp_pct,
                "idea_pct": id_pct,
            },
        }


def run_offline_check(text):
    analyzer = OfflineAnalyzer()
    return analyzer.analyze(text)


def run_web_search_check(text):
    searcher = WebSearchPlagiarism()
    return searcher.check(text)


def _ai_fallback(msg="AI service not configured"):
    return {
        "pct": 0,
        "reasons": [msg],
        "suggestions": ["Use Offline or Web Search mode instead"],
        "highlighted_sentences": [],
        "sources": [],
        "method": "ai",
        "breakdown": {"verbatim_pct": 0, "paraphrased_pct": 0, "idea_pct": 0},
    }


def run_ai_check(text, prompt_dict, mode="Standard"):
    from utils.ai_tools.ai_client import chat as _chain_chat

    system_prompt = prompt_dict.get("system", "")
    user_template = prompt_dict.get("user_template", "")
    word_count = len(text.split())
    try:
        user_prompt = user_template.format(option=mode, text=text[:8000], word_count=word_count)
    except KeyError:
        user_prompt = user_template.format(option=mode, text=text[:8000])

    try:
        raw, _used = _chain_chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            heavy=False,
            max_tokens=2048,
            timeout=60,
        )
        json_start = raw.find("{")
        json_end = raw.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            parsed = json.loads(raw[json_start:json_end])
            parsed.setdefault("pct", 10)
            parsed.setdefault("reasons", [])
            parsed.setdefault("suggestions", [])
            parsed.setdefault("highlighted_sentences", [])
            parsed.setdefault("sources", [])
            bd = parsed.get("breakdown", {})
            bd.setdefault("verbatim_pct", 0)
            bd.setdefault("paraphrased_pct", 0)
            bd.setdefault("idea_pct", 0)
            parsed["breakdown"] = bd
            parsed["method"] = "ai"
            for h in parsed.get("highlighted_sentences", []):
                h.setdefault("context_before", "")
                h.setdefault("context_after", "")
            for s in parsed.get("sources", []):
                s.setdefault("credibility", "medium")
                s.setdefault("type", "unknown")
            return parsed
        fb = _ai_fallback("AI returned unstructured response")
        fb["pct"] = 10
        return fb
    except Exception as e:
        log.error("AI check failed: %s", e)
        fb = _ai_fallback(str(e))
        return fb


def _empty_result(method="unknown", reason="Skipped"):
    return {
        "pct": 0,
        "reasons": [reason],
        "sources": [],
        "highlighted_sentences": [],
        "breakdown": {"verbatim_pct": 0, "paraphrased_pct": 0, "idea_pct": 0},
    }


def _merge_breakdown(results):
    vb = sum(r.get("breakdown", {}).get("verbatim_pct", 0) for r in results)
    pp = sum(r.get("breakdown", {}).get("paraphrased_pct", 0) for r in results)
    n = max(len(results), 1)
    return {
        "verbatim_pct": min(round(vb / n), 100),
        "paraphrased_pct": min(round(pp / n), 100),
        "idea_pct": min(round(sum(r.get("breakdown", {}).get("idea_pct", 0) for r in results) / n), 100),
    }


def _normalize_highlight(h):
    h.setdefault("context_before", "")
    h.setdefault("context_after", "")
    h.setdefault("note", "")
    return h


def _normalize_source(s):
    s.setdefault("credibility", "medium")
    s.setdefault("type", "unknown")
    return s


def run_full_scan(text, prompt_dict):
    offline_result = run_offline_check(text)
    web_result = _empty_result("web", "Web search skipped")
    try:
        web_result = run_web_search_check(text)
    except Exception as e:
        log.warning("Web search failed: %s", e)

    ai_result = _empty_result("ai", "AI check skipped")
    try:
        ai_result = run_ai_check(text, prompt_dict, "Standard")
    except Exception as e:
        log.warning("AI check failed: %s", e)

    o_pct = offline_result.get("pct", 0)
    w_pct = web_result.get("pct", 0)
    a_pct = ai_result.get("pct", 0)

    combined_pct = round(o_pct * 0.3 + w_pct * 0.4 + a_pct * 0.3)
    combined_pct = max(0, min(combined_pct, 100))

    all_reasons = []
    for src in [offline_result, web_result, ai_result]:
        for r in src.get("reasons", []):
            if r and r not in all_reasons:
                all_reasons.append(r)

    all_suggestions = []
    for src in [offline_result, web_result, ai_result]:
        for s in src.get("suggestions", []):
            if s and s not in all_suggestions:
                all_suggestions.append(s)

    severity_order = {"high": 0, "moderate": 1, "low": 2}
    all_highlights = []
    seen_h = set()
    for src in [web_result, ai_result, offline_result]:
        for h in src.get("highlighted_sentences", []):
            _normalize_highlight(h)
            key = h.get("text", "")[:100]
            if key and key not in seen_h:
                seen_h.add(key)
                all_highlights.append(h)
    all_highlights.sort(key=lambda h: severity_order.get(h.get("severity", "low"), 2))

    all_sources = []
    seen = set()
    for src in [web_result, ai_result]:
        for s in src.get("sources", []):
            _normalize_source(s)
            url = s.get("url", "")
            if url and url not in seen:
                seen.add(url)
                all_sources.append(s)

    merged_breakdown = _merge_breakdown([offline_result, web_result, ai_result])

    return {
        "pct": combined_pct,
        "reasons": all_reasons[:8],
        "suggestions": all_suggestions[:6],
        "highlighted_sentences": all_highlights[:15],
        "sources": all_sources[:10],
        "method": "full_scan",
        "breakdown": {
            "offline_pct": o_pct,
            "web_pct": w_pct,
            "ai_pct": a_pct,
            "verbatim_pct": merged_breakdown["verbatim_pct"],
            "paraphrased_pct": merged_breakdown["paraphrased_pct"],
            "idea_pct": merged_breakdown["idea_pct"],
        },
    }
