from dataclasses import asdict, dataclass, field
from typing import Optional


def _coerce_str(value) -> Optional[str]:
    """Coerce a value that should be a string into a clean string or None.

    Several upstream APIs (notably DBLP) return fields like venue/doi/title as
    a LIST when a record has multiple entries, or as a dict. Downstream code
    calls ``.lower()`` / ``.strip()`` on these fields, which crashes with
    ``'list' object has no attribute 'lower'``. Normalizing at construction
    time makes the whole pipeline list/dict-safe regardless of source.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        # Join scalar members; recurse to flatten nested/dict members.
        parts = [_coerce_str(v) for v in value]
        parts = [p for p in parts if p]
        return ", ".join(parts) if parts else None
    if isinstance(value, dict):
        # DBLP title can be {"text": "..."}; prefer common text keys.
        for k in ("text", "name", "title", "value", "#text"):
            if k in value and value[k] is not None:
                return _coerce_str(value[k])
        return None
    # int/float/bool fallthrough → string repr
    return str(value)


def _coerce_str_list(value) -> list[str]:
    """Coerce authors-like fields into a clean list of strings."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple)):
        out: list[str] = []
        for v in value:
            s = _coerce_str(v)
            if s:
                out.append(s)
        return out
    if isinstance(value, dict):
        s = _coerce_str(value)
        return [s] if s else []
    return [str(value)]


def _coerce_int(value) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, (list, tuple)):
        for v in value:
            r = _coerce_int(v)
            if r is not None:
                return r
        return None
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return None


@dataclass
class Paper:
    source: str
    source_id: str
    title: str
    authors: list[str] = field(default_factory=list)
    abstract: Optional[str] = None
    year: Optional[int] = None
    venue: Optional[str] = None
    venue_type: Optional[str] = None
    doi: Optional[str] = None
    url: Optional[str] = None
    pdf_url: Optional[str] = None
    citations: Optional[int] = None
    is_open_access: Optional[bool] = None
    type: Optional[str] = None
    publisher: Optional[str] = None
    publication_date: Optional[str] = None  # ISO date string (YYYY-MM-DD)
    db_score: Optional[float] = None  # PostgreSQL hybrid score (ts_rank + citations + recency)
    comment: Optional[str] = None  # e.g. "39 pages, 14 figures"
    fields_of_study: Optional[list[str]] = None  # e.g. ["Artificial Intelligence"]
    subjects: Optional[list[str]] = None  # e.g. ["cs.AI", "cs.LG"]
    affiliations: Optional[list[str]] = None  # author affiliations
    language: Optional[str] = None
    is_retracted: Optional[bool] = None
    funders: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)

    def __post_init__(self):
        # Normalize fields that downstream code treats as strings. Upstream
        # APIs (DBLP especially) sometimes deliver list/dict values which break
        # .lower()/.strip() calls in dedup + scoring + persist.
        self.source = _coerce_str(self.source) or ""
        self.source_id = _coerce_str(self.source_id) or ""
        self.title = _coerce_str(self.title) or ""
        self.authors = _coerce_str_list(self.authors)
        self.abstract = _coerce_str(self.abstract)
        self.venue = _coerce_str(self.venue)
        self.venue_type = _coerce_str(self.venue_type)
        self.doi = _coerce_str(self.doi)
        # DOI must be a single identifier — if upstream sent a list, keep the
        # first valid DOI rather than a comma-joined (invalid) string.
        if self.doi and "," in self.doi:
            self.doi = self.doi.split(",")[0].strip() or None
        self.url = _coerce_str(self.url)
        self.pdf_url = _coerce_str(self.pdf_url)
        self.type = _coerce_str(self.type)
        self.publisher = _coerce_str(self.publisher)
        self.keywords = _coerce_str_list(self.keywords)
        self.language = _coerce_str(self.language)
        self.funders = _coerce_str_list(self.funders)
        self.fields_of_study = _coerce_str_list(self.fields_of_study) if self.fields_of_study is not None else None
        self.subjects = _coerce_str_list(self.subjects) if self.subjects is not None else None
        self.affiliations = _coerce_str_list(self.affiliations) if self.affiliations is not None else None
        if isinstance(self.is_retracted, bool):
            pass
        elif self.is_retracted is None:
            self.is_retracted = None
        else:
            self.is_retracted = str(self.is_retracted).lower() in ("true", "1", "yes")
        self.year = _coerce_int(self.year)
        self.citations = _coerce_int(self.citations)

    def dedup_key(self) -> str:
        if self.doi:
            normalized = self.doi.strip().lower()
            normalized = normalized.removeprefix("https://doi.org/").removeprefix("http://doi.org/")
            return f"doi:{normalized}"
        return f"{self.source}:{self.source_id}"

    def to_dict(self) -> dict:
        return asdict(self)
