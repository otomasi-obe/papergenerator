"""PDF Metadata Extractor for SLR Literature Import (v2).

Extracts structured metadata from academic PDFs using font-size analysis:
- Title: largest font blocks (robust against Word junk metadata)
- Authors: lines between title and abstract
- Abstract: text after "Abstract" keyword
- DOI/Year/Venue: regex + CrossRef enrichment

Strategy:
1. Font-size analysis from PyMuPDF blocks (PRIMARY)
2. DOI regex + CrossRef API enrichment
3. Text-based fallback parsing
4. Title matching against existing SLR entries
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

import httpx
import fitz  # PyMuPDF

log = logging.getLogger(__name__)

# ─── Regex Patterns ──────────────────────────────────────────────────────────

DOI_RE = re.compile(
    r'(?:https?://(?:dx\.)?doi\.org/)?(10\.\d{4,9}/[^\s,;"\'<>]+)',
    re.IGNORECASE,
)

YEAR_RE = re.compile(r'\b(19\d{2}|20\d{2})\b')
EMAIL_RE = re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+')

# Patterns to identify journal/header noise (NOT titles)
JOURNAL_NOISE_RE = re.compile(
    r'^(?:'
    r'international\s+journal|'
    r'journal\s+of\s+|'
    r'proceedings\s+of\s+|'
    r'ieee\s+transactions|'
    r'ieee\s+access|'
    r'acm\s+transactions|'
    r'issn[\s:]|'
    r'volume\s+\d+|'
    r'www\.|'
    r'http|'
    r'©|'
    r'copyright|'
    r'\d{4,}\s*\||'          # year | format
    r'ijfmr|ijcrt|ijrti|ijert|'  # common journal abbreviations
    r'arxiv\.org|'
    r'doi[:\s]|'
    r'research\s+trends|'
    r'multidisciplinary\s+research'
    r')',
    re.IGNORECASE,
)

# Abstract header patterns (flexible)
ABSTRACT_HEADER_RE = re.compile(
    r'(?:^|\n)\s*(?:'
    r'abstract\s*[\n:.—–\-]\s*|'
    r'abstract[\s\n]+|'
    r'a\s*b\s*s\s*t\s*r\s*a\s*c\s*t\s*[\n:.—–\-]?\s*'
    r')',
    re.IGNORECASE,
)

# Section headers that end abstract
ABSTRACT_END_RE = re.compile(
    r'(?:^|\n)\s*(?:'
    r'(?:\d+\.?|i+\.?)\s+introduction|'
    r'keywords?\s*[\n:-]|'
    r'key\s*words\s*[\n:-]|'
    r'index\s+terms\s*[\n:—–\-]|'
    r'ccs\s+concepts|'
    r'categories\s+and\s+subject|'
    r'\d+\.\s+\w|'                  # numbered section
    r'i+\.\s+\w|'                     # roman numeral section
    r'1[\.\s]+introduction'
    r')',
    re.IGNORECASE | re.MULTILINE,
)

# Superscript markers in author names
SUPERSCRIPT_RE = re.compile(r'[\d*†‡§¶∥⊥#⁎]+')

# Affiliation/non-author detection
AFFILIATION_RE = re.compile(
    r'\b(?:'
    r'university|univ\b|department|dept\b|faculty|school|college|institute|'
    r'campus|academy|polytechnic|laboratory|lab\b|center|centre|research\s+group|'
    r'student|graduate|undergraduate|professor|associate|assistant|lecturer|'
    r'supervisor|fellow|scholar|researcher|'
    r'email\b|e-mail\b|corresponding\b'
    r')\b',
    re.IGNORECASE,
)

# City/geography patterns
LOCATION_RE = re.compile(
    r'^(?:[A-Z]{3,}\s*[-–]?\s*\d*|[A-Z][a-z]+\s*[-–]?\s*\d+)$|'
    r'\b(?:india|indonesia|china|japan|korea|brazil|turkey|russia|mexico|'
    r'canada|australia|germany|france|italy|spain|uk|usa|u\.s\.|united)\b',
    re.IGNORECASE,
)


def _normalize_doi(doi: str) -> str:
    doi = doi.strip().rstrip('.')
    doi = re.sub(r'^https?://(?:dx\.)?doi\.org/', '', doi)
    return doi.lower()


def _normalize_title(title: str) -> str:
    return re.sub(r'[^a-z0-9]+', '', title.lower())


def _parse_authors(authors_str: str) -> list[str]:
    """Parse author string into list. Handles comma, semicolon, 'and' separators."""
    if not authors_str:
        return []
    # Remove superscript markers
    authors_str = SUPERSCRIPT_RE.sub('', authors_str)
    authors_str = re.sub(r'\s+', ' ', authors_str).strip()
    if not authors_str:
        return []
    
    # Split on semicolons first
    if ';' in authors_str:
        parts = [a.strip() for a in authors_str.split(';') if a.strip()]
    elif ' and ' in authors_str.lower():
        parts = [a.strip() for a in re.split(r'\s+and\s+', authors_str, flags=re.I) if a.strip()]
    elif ',' in authors_str:
        parts = [a.strip() for a in authors_str.split(',') if a.strip()]
    else:
        parts = [authors_str.strip()]
    
    # Filter out emails, empty, affiliations
    filtered = []
    for p in parts:
        p = p.strip()
        if not p or len(p) < 2:
            continue
        if EMAIL_RE.match(p):
            continue
        # Skip affiliation-like parts
        if re.match(r'^(student|professor|researcher|lecturer|assistant|associate|department|faculty|school|university|college|institute|lab)', p, re.I):
            continue
        # Must have at least one letter
        if not re.search(r'[a-zA-Z]', p):
            continue
        filtered.append(p)
    return filtered


# ─── Font-Size Based Extraction ──────────────────────────────────────────────

def _get_page_lines(page) -> list[dict]:
    """Extract text lines with font size from a page using dict mode."""
    lines = []
    try:
        blocks = page.get_text('dict')['blocks']
    except Exception:
        return lines
    
    for block in blocks:
        if block.get('type') != 0:
            continue
        for line in block.get('lines', []):
            spans = line.get('spans', [])
            if not spans:
                continue
            text = ''.join(s.get('text', '') for s in spans).strip()
            if not text:
                continue
            # Use dominant font size (largest span)
            font_size = max(s.get('size', 0) for s in spans)
            font_name = spans[0].get('font', '')
            lines.append({
                'text': text,
                'size': round(font_size, 1),
                'font': font_name,
                'is_bold': 'bold' in font_name.lower() or 'medi' in font_name.lower(),
            })
    return lines


def _extract_title_by_fontsize(lines: list[dict]) -> tuple[str, int]:
    """Find title by identifying the largest font size lines.
    
    Returns (title, line_index) where line_index is where title ends.
    """
    if not lines:
        return '', 0
    
    # Find max font size
    max_size = max(l['size'] for l in lines)
    
    # Collect all lines at max font size (title may wrap across lines)
    # But filter out journal headers that happen to be same size
    title_lines = []
    title_end_idx = 0
    
    for i, line in enumerate(lines):
        if line['size'] >= max_size - 1.0:  # within 1pt of max
            text = line['text']
            # Skip journal/header noise
            if JOURNAL_NOISE_RE.search(text):
                continue
            if len(text) < 5:
                continue
            # Skip ISSN/paper IDs like IJCRT2406111
            if re.match(r'^[a-z]+\d{3,}$', text, re.I):
                continue
            title_lines.append(text)
            title_end_idx = i + 1
        elif title_lines:
            # Once we've started collecting title, stop at smaller font
            break
    
    if not title_lines:
        return '', 0
    
    # Join title lines, fix hyphenation at line breaks
    title = ' '.join(title_lines)
    # Fix: "Low-\ncost" → "Low-cost", "Proportional-Integral-\nDerivative" → "Proportional-Integral-Derivative"
    # Only remove hyphens at end of a title piece (hyphenation break), not intentional hyphens
    # Strategy: join first, then fix cases where a word ends with hyphen
    title = re.sub(r'(\w)-\s+', r'\1-', title)  # "Proportional-Integral- Derivative" → "Proportional-Integral-Derivative"
    title = re.sub(r'\s+', ' ', title).strip()
    return title[:300], title_end_idx


def _extract_authors_by_position(lines: list[dict], title_end_idx: int) -> list[str]:
    """Extract authors from lines between title and abstract."""
    authors = []
    hit_affiliation = False
    
    for i in range(title_end_idx, min(title_end_idx + 10, len(lines))):
        line = lines[i]
        text = line['text']
        
        # Stop at abstract
        if re.match(r'^(?:abstract|a\s*b\s*s\s*t\s*r\s*a\s*c\s*t)\s*[\n:.—–\-]', text, re.I):
            break
        
        # Stop at section headers
        if re.match(r'^\d+\.\s|^i+\.\s', text, re.I):
            break
        
        # Skip known non-author content
        if EMAIL_RE.search(text) and not re.search(r'[A-Z][a-z]+\s+[A-Z][a-z]+', text):
            continue
        if re.match(r'^(doi|http|www|©|journal|vol|issue)', text, re.I):
            continue
        
        # STRONG STOP: if we've already found authors and now hit affiliation, stop
        if AFFILIATION_RE.search(text):
            hit_affiliation = True
            if authors:
                break  # already have authors, this is just affiliation
            continue
        
        # Stop at purely location-like lines
        if LOCATION_RE.search(text) and not re.search(r'[A-Z][a-z]+\s+[A-Z][a-z]+', text):
            if authors:
                break
            continue
        
        # If we hit affiliation line and then this line has no names, stop
        if hit_affiliation and not re.search(r'[A-Z][a-z]+\s+[A-Z][a-z]+', text):
            break
        
        # Remove superscript markers for analysis
        cleaned = SUPERSCRIPT_RE.sub('', text)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        
        # Author indicators: names separated by commas, "and", or with superscripts
        has_name_pattern = bool(re.search(r'[A-Z][a-z]+\s+[A-Z]', cleaned))
        has_comma_sep = ',' in cleaned and bool(re.search(r'[A-Z][a-z]+', cleaned))
        has_and = ' and ' in cleaned.lower()
        has_superscript = bool(SUPERSCRIPT_RE.search(text)) and bool(re.search(r'[A-Z][a-z]+', cleaned))
        
        if has_name_pattern or has_comma_sep or has_and or has_superscript:
            # Clean up superscript markers from names
            cleaned = SUPERSCRIPT_RE.sub('', text)
            # Remove "∗" (arxiv asterisk)
            cleaned = cleaned.replace('∗', '').replace('*', '').replace('†', '')
            # Remove numbered affiliation markers like "1Student, 2Student..."
            cleaned = re.sub(r'\d+\s*(?:student|professor|assistant|associate|lecturer|researcher|pg\s*students?)[s,]*', '', cleaned, flags=re.I)
            cleaned = re.sub(r'\d+,', ',', cleaned)  # "1Abhishek," → "Abhishek,"
            cleaned = re.sub(r'^\d+', '', cleaned)  # leading numbers like "1Abhishek"
            cleaned = re.sub(r'\s+', ' ', cleaned).strip()
            if cleaned:
                authors.extend(_parse_authors(cleaned))
    
    return authors


def _extract_abstract_by_keyword(lines: list[dict], full_text: str) -> str:
    """Extract abstract using keyword detection."""
    abstract_match = re.search(
        r'(?:abstract|a\s*b\s*s\s*t\s*r\s*a\s*c\s*t)\s*[\n:.—–\-]+\s*',
        full_text, re.I
    )
    
    if not abstract_match:
        # Try simpler pattern: just "Abstract " followed by text
        abstract_match = re.search(r'\babstract\b\s+', full_text, re.I)
    
    if not abstract_match:
        return ''
    
    start = abstract_match.end()
    remaining = full_text[start:]
    
    # Find end of abstract
    end_match = ABSTRACT_END_RE.search(remaining)
    if end_match:
        abstract = remaining[:end_match.start()]
    else:
        # Take first ~400 words
        words = remaining.split()
        abstract = ' '.join(words[:400])
    
    # Clean up
    abstract = re.sub(r'\s+', ' ', abstract).strip()
    # Remove trailing incomplete sentences
    if abstract and not abstract.endswith('.'):
        last_period = abstract.rfind('.')
        if last_period > len(abstract) * 0.7:
            abstract = abstract[:last_period + 1]
    
    return abstract[:3000]


def _extract_doi_from_text(text: str) -> str | None:
    match = DOI_RE.search(text[:5000])
    return _normalize_doi(match.group(1)) if match else None


def _extract_year_from_text(text: str) -> int | None:
    patterns = [
        r'(?:published|received|accepted|online|available)[:\s]+\d{1,2}\s+\w+\s+(\d{4})',
        r'(?:published|received|accepted|online|available)[:\s]+\w+\s+\d{1,2},?\s+(\d{4})',
        r'©\s*(\d{4})',
        r'\((\d{4})\)',
        r'(?:vol|volume|iss|issue)\s*\d+.*?(\d{4})',
        r'(\d{4})\s*(?:IEEE|ACM|Springer|Elsevier|Wiley|Oxford|Cambridge)',
        r'(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{4})',
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            year = int(m.group(1))
            if 1990 <= year <= 2030:
                return year
    
    # Fallback: first year in range
    for m in YEAR_RE.finditer(text[:3000]):
        year = int(m.group(1))
        if 2000 <= year <= 2030:
            return year
    return None


def _extract_venue_from_text(text: str) -> str:
    patterns = [
        r'(International\s+Journal\s+(?:of|for)\s+[^\n(,]+)',
        r'(IEEE\s+(?:Transactions|Journal|Conference|Symposium|Workshop)[^\n,]+)',
        r'(ACM\s+(?:Transactions|Journal|Conference|Symposium|SIG\w+)[^\n,]+)',
        r'(?:published\s+in|appears\s+in|presented\s+at)\s+[:\s]*([^\n,]+)',
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            venue = m.group(1).strip()
            if 5 < len(venue) < 200:
                return venue
    return ''


def _extract_keywords_from_text(text: str) -> list[str]:
    m = re.search(
        r'(?:keywords?|key\s*words|index\s+terms)\s*[\n:—–\-]+\s*(.+?)(?:\n\n|\n[A-Z]|\n\d+\.)',
        text, re.I | re.DOTALL
    )
    if m:
        kw_text = m.group(1).strip()
        kws = [k.strip().rstrip('.') for k in re.split(r'[,;]', kw_text) if k.strip()]
        return kws[:15]
    return []


def _enrich_from_doi(doi: str) -> dict | None:
    """Enrich metadata from DOI via CrossRef API."""
    if not doi:
        return None
    
    url = f"https://api.crossref.org/works/{doi}"
    headers = {
        'User-Agent': 'PaperGenerator/1.0 (mailto:rofiqcp@gmail.com)',
        'Accept': 'application/json',
    }
    
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(url, headers=headers)
            if resp.status_code != 200:
                log.warning("CrossRef DOI lookup failed for %s: %d", doi, resp.status_code)
                return None
            
            data = resp.json().get('message', {})
            
            title = ''
            if data.get('title'):
                title = data['title'][0] if isinstance(data['title'], list) else data['title']
            
            authors = []
            for author in data.get('author', []):
                name = f"{author.get('given', '')} {author.get('family', '')}".strip()
                if name:
                    authors.append(name)
            
            year = None
            date_parts = data.get('published-print', data.get('published-online', data.get('issued', {})))
            if date_parts and date_parts.get('date-parts'):
                try:
                    parts = date_parts['date-parts'][0]
                    if parts and isinstance(parts, (list, tuple)) and parts[0]:
                        year = parts[0]
                except (IndexError, TypeError):
                    pass
            
            venue = ''
            if data.get('container-title'):
                venue = data['container-title'][0] if isinstance(data['container-title'], list) else data['container-title']
            elif data.get('event', {}).get('name'):
                venue = data['event']['name']
            
            publisher = data.get('publisher', '')
            
            abstract = data.get('abstract', '')
            if abstract:
                abstract = re.sub(r'<[^>]+>', '', abstract).strip()
            
            return {
                'title': title,
                'authors': authors,
                'year': year,
                'venue': venue,
                'publisher': publisher,
                'abstract': abstract[:3000] if abstract else '',
            }
    except Exception as e:
        log.warning("CrossRef enrichment failed for DOI %s: %s", doi, e)
        return None


# ─── Main Entry Point ────────────────────────────────────────────────────────

def extract_metadata_from_pdf(
    filepath: Path,
    existing_dois: set[str] | None = None,
    existing_titles_norm: set[str] | None = None,
) -> dict:
    """Extract metadata from a PDF file using font-size analysis.
    
    Returns dict with keys: title, authors, year, doi, abstract, venue,
    publisher, keywords, source_kind, match_id, match_type
    """
    metadata = {
        'title': '',
        'authors': [],
        'year': None,
        'doi': None,
        'abstract': '',
        'venue': '',
        'publisher': '',
        'keywords': [],
        'source_kind': 'file',
        'match_id': None,
        'match_type': None,
    }
    
    filepath = Path(filepath)
    
    try:
        doc = fitz.open(str(filepath))
    except Exception as e:
        log.error("Failed to open PDF %s: %s", filepath, e)
        metadata['title'] = filepath.stem.replace('_', ' ').replace('-', ' ').title()
        return metadata
    
    if doc.is_encrypted:
        log.warning("PDF is encrypted: %s", filepath)
        doc.close()
        metadata['title'] = filepath.stem.replace('_', ' ').replace('-', ' ').title()
        return metadata
    
    # ─── Step 1: Extract text + font info from first pages ───────────────────
    first_page_lines = _get_page_lines(doc[0])
    
    # Full text for regex matching
    first_pages_text = ''
    try:
        for i in range(min(2, len(doc))):
            try:
                page = doc[i]
                text = page.get_text("text")
                if text.strip():
                    first_pages_text += text + '\n\n'
            except Exception as e:
                log.warning("Failed to extract text from page %d: %s", i, e)
    finally:
        doc.close()
    
    # ─── Step 2: Font-size based title extraction (PRIMARY) ──────────────────
    title, title_end_idx = _extract_title_by_fontsize(first_page_lines)
    if title:
        metadata['title'] = title
    
    # ─── Step 3: Authors from position analysis ──────────────────────────────
    if title_end_idx > 0:
        metadata['authors'] = _extract_authors_by_position(first_page_lines, title_end_idx)
    
    # ─── Step 4: DOI from text ───────────────────────────────────────────────
    metadata['doi'] = _extract_doi_from_text(first_pages_text)
    
    # ─── Step 5: Year from text ──────────────────────────────────────────────
    metadata['year'] = _extract_year_from_text(first_pages_text)
    
    # ─── Step 6: Abstract from keyword detection ─────────────────────────────
    metadata['abstract'] = _extract_abstract_by_keyword(first_page_lines, first_pages_text)
    
    # ─── Step 7: Venue from text ─────────────────────────────────────────────
    metadata['venue'] = _extract_venue_from_text(first_pages_text)
    
    # ─── Step 8: Keywords from text ──────────────────────────────────────────
    metadata['keywords'] = _extract_keywords_from_text(first_pages_text)
    
    # ─── Step 9: PDF metadata as FALLBACK only ───────────────────────────────
    # Only use if text extraction failed (encrypted, scanned PDF, etc.)
    pdf_meta = {}
    if not metadata['title']:
        try:
            doc = fitz.open(str(filepath))
            pdf_meta = doc.metadata or {}
            doc.close()
        except Exception:
            pass
        
        meta_title = pdf_meta.get('title', '').strip()
        # Validate: reject junk metadata (journal abbreviations, single words)
        if meta_title and len(meta_title) > 10 and not JOURNAL_NOISE_RE.search(meta_title):
            metadata['title'] = meta_title
    
    if not metadata['authors'] and pdf_meta.get('author'):
        author_str = pdf_meta['author'].strip()
        # Reject common junk: "Dell", "baps", "Microsoft", "unknown"
        if author_str and author_str.lower() not in ('none', 'unknown', 'microsoft', 'adobe', 'dell', 'baps', 'hp'):
            if len(author_str) > 3 and ' ' in author_str:  # must have space (first + last name)
                metadata['authors'] = _parse_authors(author_str)
    
    if not metadata['doi']:
        for key in ('doi', 'DOI'):
            val = pdf_meta.get(key, '')
            if val:
                m = DOI_RE.search(val)
                if m:
                    metadata['doi'] = _normalize_doi(m.group(1))
                    break
    
    if not metadata['abstract'] and pdf_meta.get('subject'):
        metadata['abstract'] = pdf_meta['subject'].strip()[:3000]
    
    if not metadata['keywords'] and pdf_meta.get('keywords'):
        metadata['keywords'] = [
            k.strip() for k in re.split(r'[;,]', pdf_meta['keywords']) if k.strip()
        ]
    
    # ─── Step 10: Fallback title from filename ───────────────────────────────
    if not metadata['title']:
        metadata['title'] = filepath.stem.replace('_', ' ').replace('-', ' ').title()[:300]
    
    # ─── Step 11: CrossRef enrichment ────────────────────────────────────────
    if metadata['doi'] and (not metadata['authors'] or not metadata['year'] or not metadata['venue']):
        enriched = _enrich_from_doi(metadata['doi'])
        if enriched:
            if not metadata['title'] or len(enriched.get('title', '')) > len(metadata['title']):
                metadata['title'] = enriched['title']
            if not metadata['authors'] and enriched.get('authors'):
                metadata['authors'] = enriched['authors']
            if not metadata['year'] and enriched.get('year'):
                metadata['year'] = enriched['year']
            if not metadata['venue'] and enriched.get('venue'):
                metadata['venue'] = enriched['venue']
            if not metadata['publisher'] and enriched.get('publisher'):
                metadata['publisher'] = enriched['publisher']
            if not metadata['abstract'] and enriched.get('abstract'):
                metadata['abstract'] = enriched['abstract']
    
    # ─── Step 12: Match against existing SLR entries ─────────────────────────
    if existing_dois and metadata['doi']:
        doi_norm = metadata['doi'].lower().strip()
        if doi_norm in existing_dois:
            metadata['match_type'] = 'doi'
    
    if not metadata['match_type'] and existing_titles_norm:
        title_norm = _normalize_title(metadata['title'])
        if title_norm in existing_titles_norm:
            metadata['match_type'] = 'title'
    
    return metadata