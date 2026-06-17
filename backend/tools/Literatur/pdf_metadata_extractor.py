"""PDF Metadata Extractor for SLR Literature Import.

Extracts structured metadata from academic PDFs:
- Title, Authors, Year, DOI, Abstract, Venue, Publisher

Strategy:
1. PyMuPDF XMP/metadata (fast, structured)
2. Text-based parsing from first page (fallback)
3. DOI lookup via CrossRef/Semantic Scholar (enrichment)
4. Title matching against existing SLR entries (sync)
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Optional

import httpx
import fitz  # PyMuPDF

log = logging.getLogger(__name__)

# ─── Regex Patterns ──────────────────────────────────────────────────────────

# DOI pattern: 10.XXXX/... (with optional URL prefix)
DOI_RE = re.compile(
    r'(?:https?://(?:dx\.)?doi\.org/)?(10\.\d{4,9}/[^\s,;"\'<>]+)',
    re.IGNORECASE,
)

# Year pattern: 4-digit year in [1900, current_year+1]
YEAR_RE = re.compile(r'\b(19\d{2}|20\d{2})\b')

# Email pattern for author detection
EMAIL_RE = re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+')

# Common section headers that mark end of abstract
ABSTRACT_END_MARKERS = re.compile(
    r'^(?:\d+\.?\s+)?(?:introduction|background|keywords|key\s*words|'
    r'index\s+terms|1\.\s|introduction\s*\n|ccs\s+concepts|'
    r'categories\s+and\s+subject|general\s+terms|keywords?\s*[:\n])',
    re.IGNORECASE | re.MULTILINE,
)

# Common keywords section
KEYWORDS_RE = re.compile(
    r'(?:keywords?|key\s*words|index\s+terms)\s*[:\n]\s*(.+?)(?:\n\n|\n[A-Z])',
    re.IGNORECASE | re.DOTALL,
)


def extract_metadata_from_pdf(
    filepath: Path,
    existing_dois: set[str] | None = None,
    existing_titles_norm: set[str] | None = None,
) -> dict:
    """Extract metadata from a PDF file.
    
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
    
    try:
        doc = fitz.open(str(filepath))
    except Exception as e:
        log.error("Failed to open PDF %s: %s", filepath, e)
        metadata['title'] = filepath.stem.replace('_', ' ').replace('-', ' ').title()
        return metadata
    
    # Check for encrypted PDF
    if doc.is_encrypted:
        log.warning("PDF is encrypted: %s", filepath)
        doc.close()
        metadata['title'] = filepath.stem.replace('_', ' ').replace('-', ' ').title()
        return metadata
    
    # ─── Step 1: Extract from PDF metadata / XMP ─────────────────────────────
    pdf_meta = doc.metadata or {}
    
    # Title from metadata
    if pdf_meta.get('title') and len(pdf_meta['title'].strip()) > 3:
        metadata['title'] = pdf_meta['title'].strip()
    
    # Authors from metadata
    if pdf_meta.get('author'):
        authors_str = pdf_meta['author'].strip()
        if authors_str and authors_str.lower() not in ('none', 'unknown', 'microsoft', 'adobe'):
            metadata['authors'] = _parse_authors(authors_str)
    
    # DOI from metadata
    doi_from_meta = None
    for key in ('doi', 'DOI', 'xmp:DOI'):
        val = pdf_meta.get(key, '')
        if val:
            m = DOI_RE.search(val)
            if m:
                doi_from_meta = _normalize_doi(m.group(1))
                break
    
    # Subject/Keywords
    if pdf_meta.get('subject'):
        metadata['abstract'] = pdf_meta['subject'].strip()[:3000]
    if pdf_meta.get('keywords'):
        metadata['keywords'] = [
            k.strip() for k in re.split(r'[;,]', pdf_meta['keywords']) if k.strip()
        ]
    
    # ─── Step 2: Extract from first pages text ───────────────────────────────
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
    
    # DOI: prefer metadata, then search text
    if doi_from_meta:
        metadata['doi'] = doi_from_meta
    else:
        doi_match = DOI_RE.search(first_pages_text[:5000])
        if doi_match:
            metadata['doi'] = _normalize_doi(doi_match.group(1))
    
    # Title: if not from metadata, extract from first page
    if not metadata['title']:
        metadata['title'] = _extract_title_from_text(first_pages_text)
    
    # Fallback title from filename
    if not metadata['title']:
        metadata['title'] = filepath.stem.replace('_', ' ').replace('-', ' ').title()[:300]
    
    # Authors: if not from metadata, try to parse from text
    if not metadata['authors']:
        metadata['authors'] = _extract_authors_from_text(first_pages_text)
    
    # Year: try from text
    if not metadata['year']:
        metadata['year'] = _extract_year_from_text(first_pages_text)
    
    # Abstract: if not from subject, extract from text
    if not metadata['abstract']:
        metadata['abstract'] = _extract_abstract_from_text(first_pages_text)
    
    # Venue: try from text
    if not metadata['venue']:
        metadata['venue'] = _extract_venue_from_text(first_pages_text)
    
    # ─── Step 3: DOI enrichment via CrossRef ─────────────────────────────────
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
    
    # ─── Step 4: Match against existing SLR entries ──────────────────────────
    if existing_dois and metadata['doi']:
        doi_norm = metadata['doi'].lower().strip()
        if doi_norm in existing_dois:
            metadata['match_type'] = 'doi'
    
    if not metadata['match_type'] and existing_titles_norm:
        title_norm = _normalize_title(metadata['title'])
        if title_norm in existing_titles_norm:
            metadata['match_type'] = 'title'
    
    return metadata


# ─── Helper Functions ────────────────────────────────────────────────────────

def _normalize_doi(doi: str) -> str:
    """Clean DOI string."""
    doi = doi.strip().rstrip('.')
    # Remove URL prefix
    doi = re.sub(r'^https?://(?:dx\.)?doi\.org/', '', doi)
    return doi.lower()


def _normalize_title(title: str) -> str:
    """Normalize title for matching: lowercase, strip non-alphanumeric."""
    return re.sub(r'[^a-z0-9]+', '', title.lower())


def _parse_authors(authors_str: str) -> list[str]:
    """Parse author string into list. Handles comma and 'and' separators."""
    if not authors_str:
        return []
    # Split on semicolons first (common in academic papers)
    if ';' in authors_str:
        parts = [a.strip() for a in authors_str.split(';') if a.strip()]
    elif ' and ' in authors_str:
        parts = [a.strip() for a in re.split(r'\s+and\s+', authors_str) if a.strip()]
    elif ',' in authors_str:
        parts = [a.strip() for a in authors_str.split(',') if a.strip()]
    else:
        parts = [authors_str.strip()]
    return [p for p in parts if len(p) > 1 and not EMAIL_RE.match(p)]


def _extract_title_from_text(text: str) -> str:
    """Extract title from first page text.
    
    Heuristic: title is usually the first substantial line that isn't a 
    journal header, page number, or institutional info.
    """
    lines = text.split('\n')
    candidates = []
    
    for line in lines[:30]:
        line = line.strip()
        if not line:
            continue
        # Skip common header noise
        if len(line) < 5:
            continue
        if re.match(r'^(vol|volume|issue|page|pp\.|doi|http|www|©|journal|received|accepted|published)', line, re.I):
            continue
        if re.match(r'^\d+$', line):  # page numbers
            continue
        if EMAIL_RE.search(line):
            continue
        if len(line) > 10:
            candidates.append(line)
    
    if not candidates:
        return ''
    
    # Title is typically the longest of the first 1-3 candidates
    # (sometimes title wraps across 2 lines)
    title_parts = []
    for c in candidates[:3]:
        title_parts.append(c)
        # If this line ends with a period or is >60 chars, probably standalone
        if c.endswith('.') or len(c) > 60:
            break
    
    title = ' '.join(title_parts).strip()
    # Clean up
    title = re.sub(r'\s+', ' ', title)
    return title[:300]


def _extract_authors_from_text(text: str) -> list[str]:
    """Extract authors from first page text.
    
    Heuristic: authors appear after the title, before the abstract.
    They look like names (capitalized words, possibly with superscript numbers).
    """
    lines = text.split('\n')
    # Find the abstract marker to know where to stop looking
    abstract_start = len(lines)
    for i, line in enumerate(lines):
        if re.match(r'^(abstract|a b s t r a c t|a\s*b\s*s\s*t\s*r\s*a\s*c\s*t)', line.strip(), re.I):
            abstract_start = i
            break
    
    # Authors are typically in lines 2-10, before abstract
    author_candidates = []
    for line in lines[1:min(abstract_start, 15)]:
        line = line.strip()
        if not line or len(line) < 3:
            continue
        # Skip lines that are clearly not author lines
        if re.match(r'^(doi|http|www|©|journal|vol|issue|page|received|accepted|published)', line, re.I):
            continue
        if re.match(r'^\d+$', line):
            continue
        # Author lines typically have capitalized names separated by commas or 'and'
        # They might have superscript numbers like "John Smith1, Jane Doe2"
        cleaned = re.sub(r'[\d*†‡§¶∥⊥#]+', '', line).strip()
        cleaned = re.sub(r'\s+', ' ', cleaned)
        
        # Check if it looks like names (at least 2 words, mostly letters)
        words = cleaned.replace(',', ' ').replace(';', ' ').split()
        name_words = [w for w in words if re.match(r'^[A-Z][a-z]+$', w)]
        
        if len(name_words) >= 2 and len(cleaned) > 5:
            # Looks like an author line
            author_candidates.append(cleaned)
    
    if not author_candidates:
        return []
    
    # Combine first author-like line(s)
    combined = ' '.join(author_candidates[:2])
    # Remove email addresses
    combined = EMAIL_RE.sub('', combined)
    # Remove affiliation keywords
    combined = re.sub(r'\b(university|department|institute|school|faculty|college|center|centre|lab|laboratory)\b.*?(?:,|;|$)', '', combined, flags=re.I)
    
    return _parse_authors(combined)


def _extract_year_from_text(text: str) -> int | None:
    """Extract publication year from first page text."""
    # Look for year in common formats
    patterns = [
        r'(?:published|received|accepted|online|available)[:\s]+\d{1,2}\s+\w+\s+(\d{4})',
        r'(?:published|received|accepted|online|available)[:\s]+\w+\s+\d{1,2},?\s+(\d{4})',
        r'©\s*(\d{4})',
        r'\((\d{4})\)',
        r'(?:vol|volume|iss|issue)\s*\d+.*?(\d{4})',
        r'(\d{4})\s*(?:IEEE|ACM|Springer|Elsevier|Wiley|Oxford|Cambridge)',
    ]
    
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            year = int(m.group(1))
            if 1990 <= year <= 2030:
                return year
    
    # Fallback: first 4-digit year in reasonable range
    for m in YEAR_RE.finditer(text[:3000]):
        year = int(m.group(1))
        if 2000 <= year <= 2030:
            return year
    
    return None


def _extract_abstract_from_text(text: str) -> str:
    """Extract abstract from first page text."""
    # Find "Abstract" header
    abstract_match = re.search(
        r'(?:^|\n)\s*(?:a\s*b\s*s\s*t\s*r\s*a\s*c\s*t|abstract)\s*[\n:.-]\s*',
        text, re.I
    )
    if not abstract_match:
        # Try without header (some papers just start with abstract)
        return ''
    
    start = abstract_match.end()
    remaining = text[start:]
    
    # Find end of abstract (next section header)
    end_match = ABSTRACT_END_MARKERS.search(remaining)
    if end_match:
        abstract = remaining[:end_match.start()]
    else:
        # Take first ~500 words if no clear end marker
        words = remaining.split()
        abstract = ' '.join(words[:500])
    
    abstract = re.sub(r'\s+', ' ', abstract).strip()
    return abstract[:3000]


def _extract_venue_from_text(text: str) -> str:
    """Extract venue/journal name from first page text."""
    patterns = [
        # Journal/conference names at top of page
        r'^(?:journal|proceedings|conference|transactions|international\s+journal)\s*[:\n]?\s*(.+?)(?:\n|$)',
        # IEEE format
        r'(IEEE\s+(?:Transactions|Journal|Conference|Symposium|Workshop)[^\n,]+)',
        # ACM format
        r'(ACM\s+(?:Transactions|Journal|Conference|Symposium|SIG\w+)[^\n,]+)',
        # Common venue patterns
        r'(?:published\s+in|appears\s+in|presented\s+at)\s+[:\s]*([^\n,]+)',
    ]
    
    for pattern in patterns:
        m = re.search(pattern, text, re.I | re.M)
        if m:
            venue = m.group(1).strip()
            if 5 < len(venue) < 200:
                return venue
    
    return ''


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
            
            # Title
            title = ''
            if data.get('title'):
                title = data['title'][0] if isinstance(data['title'], list) else data['title']
            
            # Authors
            authors = []
            for author in data.get('author', []):
                name = f"{author.get('given', '')} {author.get('family', '')}".strip()
                if name:
                    authors.append(name)
            
            # Year
            year = None
            date_parts = data.get('published-print', data.get('published-online', data.get('issued', {})))
            if date_parts and date_parts.get('date-parts'):
                try:
                    parts = date_parts['date-parts'][0]
                    if parts and isinstance(parts, (list, tuple)) and parts[0]:
                        year = parts[0]
                except (IndexError, TypeError):
                    pass
            
            # Venue
            venue = ''
            if data.get('container-title'):
                venue = data['container-title'][0] if isinstance(data['container-title'], list) else data['container-title']
            elif data.get('event', {}).get('name'):
                venue = data['event']['name']
            
            # Publisher
            publisher = data.get('publisher', '')
            
            # Abstract (may have HTML tags)
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
