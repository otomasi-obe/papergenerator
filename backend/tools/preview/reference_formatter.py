"""
Reference Formatter — Format structured reference objects into citation strings.
=================================================================================
Each reference from the AI is now a structured JSON object with metadata fields
(authors, year, title, type, journal, volume, pages, doi, etc.). This module
formats them into display strings according to the selected citation style.

Supported styles: IEEE, APA, Harvard, Chicago, Vancouver, MLA, ACS.
Backward compatible: if a reference is already a string, it's returned as-is.
"""

from __future__ import annotations


def format_reference(ref, style: str = "ieee", index: int = 1) -> str:
    """Format a single reference object (or string) into a citation string.

    Args:
        ref: Either a string (returned as-is) or a dict with structured metadata.
        style: Citation style slug (case-insensitive). One of:
               ieee, apa, harvard, chicago, vancouver, mla, acs.
        index: 1-based reference number (used for numbered styles like IEEE/Vancouver).

    Returns:
        Formatted reference string.
    """
    if isinstance(ref, str):
        return ref
    if not isinstance(ref, dict):
        return str(ref)

    style = (style or "ieee").lower().strip()

    authors = ref.get("authors", [])
    year = ref.get("year", "")
    title = ref.get("title", "")
    ref_type = (ref.get("type") or "journal").lower()
    journal = ref.get("journal", "")
    conference = ref.get("conference", "")
    volume = ref.get("volume", "")
    issue = ref.get("issue", "")
    pages = ref.get("pages", "")
    doi = ref.get("doi", "")
    publisher = ref.get("publisher", "")
    location = ref.get("location", "")
    url = ref.get("url", "")
    accessed = ref.get("accessed", "")
    editors = ref.get("editors", [])
    book_title = ref.get("book_title", "")
    institution = ref.get("institution", "")

    dispatch = {
        "ieee": _fmt_ieee,
        "apa": _fmt_apa,
        "harvard": _fmt_harvard,
        "chicago": _fmt_chicago,
        "vancouver": _fmt_vancouver,
        "mla": _fmt_mla,
        "acs": _fmt_acs,
    }
    formatter = dispatch.get(style, _fmt_ieee)
    return formatter(
        authors=authors, year=year, title=title, ref_type=ref_type,
        journal=journal, conference=conference, volume=volume, issue=issue,
        pages=pages, doi=doi, publisher=publisher, location=location,
        url=url, accessed=accessed, editors=editors, book_title=book_title,
        institution=institution, index=index,
    )


def format_references_list(references, style: str = "ieee") -> list[str]:
    """Format a list of references (mixed strings/objects) into display strings.

    Args:
        references: List of reference items (strings or dicts).
        style: Citation style slug.

    Returns:
        List of formatted reference strings.
    """
    if not isinstance(references, list):
        return []
    result = []
    for i, ref in enumerate(references, 1):
        result.append(format_reference(ref, style=style, index=i))
    return result


# ── Helpers ────────────────────────────────────────────────────────────────────

def _join_authors(authors: list, fmt: str = "full") -> str:
    """Join author names according to style convention.

    fmt:
      "initials_last"  → "A. B. Lastname" (IEEE style)
      "last_initials"  → "Lastname, A. B." (APA style)
      "last_initials_noperiod" → "Lastname AB" (Vancouver style)
      "full"           → "Firstname Lastname" (Chicago style)
    """
    if not authors:
        return ""
    parts = []
    for a in authors:
        if fmt == "initials_last":
            # Expect "Lastname, Initials" or "Lastname Initials"
            parts.append(a)
        elif fmt == "last_initials":
            parts.append(a)
        elif fmt == "last_initials_noperiod":
            # Strip periods from initials
            parts.append(a.replace(".", ""))
        elif fmt == "full":
            parts.append(a)
        else:
            parts.append(a)
    if len(parts) == 1:
        return parts[0]
    elif len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    else:
        return ", ".join(parts[:-1]) + f", and {parts[-1]}"


# ── Style Formatters ───────────────────────────────────────────────────────────

def _fmt_ieee(**kw) -> str:
    """[N] A. B. Author, "Title," Journal, vol. X, no. Y, pp. Z, Year, doi."""
    idx = kw["index"]
    authors = _join_authors(kw["authors"], "initials_last")
    title = kw["title"]
    year = kw["year"]
    ref_type = kw["ref_type"]

    if ref_type == "book":
        s = f'[{idx}] {authors}, {title}.'
        if kw["publisher"]:
            s += f' {kw["location"]}: {kw["publisher"]},' if kw["location"] else f' {kw["publisher"]},'
        s += f' {year}.'
    elif ref_type == "conference":
        s = f'[{idx}] {authors}, "{title}," in Proc. {kw["conference"]}, {year}'
        if kw["pages"]:
            s += f', pp. {kw["pages"]}'
        s += '.'
    elif ref_type == "thesis":
        s = f'[{idx}] {authors}, "{title}," {kw["institution"]}, {year}.'
    elif ref_type == "website":
        s = f'[{idx}] {authors}. ({year}). {title}. [Online]. Available: {kw["url"]}'
        if kw["accessed"]:
            s += f' (Accessed: {kw["accessed"]}).'
        else:
            s += '.'
    else:  # journal
        s = f'[{idx}] {authors}, "{title},"'
        if kw["journal"]:
            s += f' {kw["journal"]},'
        if kw["volume"]:
            s += f' vol. {kw["volume"]},'
        if kw["issue"]:
            s += f' no. {kw["issue"]},'
        if kw["pages"]:
            s += f' pp. {kw["pages"]},'
        s += f' {year}.'
    if kw["doi"]:
        s += f' doi: {kw["doi"]}.'
    return s


def _fmt_apa(**kw) -> str:
    """Author, A. B. (Year). Title. Journal, Volume(Issue), Pages. https://doi.org/"""
    authors = _join_authors(kw["authors"], "last_initials")
    year = kw["year"]
    title = kw["title"]
    ref_type = kw["ref_type"]

    if ref_type == "book":
        s = f'{authors} ({year}). {title}.'
        if kw["publisher"]:
            s += f' {kw["publisher"]}.'
    elif ref_type == "conference":
        s = f'{authors} ({year}). {title}. In {kw["conference"]}'
        if kw["pages"]:
            s += f' (pp. {kw["pages"]})'
        s += '.'
    elif ref_type == "thesis":
        s = f'{authors} ({year}). {title} [Doctoral dissertation, {kw["institution"]}].'
    elif ref_type == "website":
        s = f'{authors} ({year}). {title}. {kw["url"]}'
    else:  # journal
        s = f'{authors} ({year}). {title}.'
        if kw["journal"]:
            s += f' {kw["journal"]},'
        if kw["volume"]:
            s += f' {kw["volume"]}'
        if kw["issue"]:
            s += f'({kw["issue"]})'
        s += ','
        if kw["pages"]:
            s += f' {kw["pages"]}.'
        else:
            s = s.rstrip(',') + '.'
    if kw["doi"]:
        s += f' https://doi.org/{kw["doi"]}'
    return s


def _fmt_harvard(**kw) -> str:
    """Author, A.B. (Year) 'Title', Journal, Volume(Issue), pp. Pages."""
    authors = _join_authors(kw["authors"], "last_initials")
    year = kw["year"]
    title = kw["title"]
    ref_type = kw["ref_type"]

    if ref_type == "book":
        s = f'{authors} ({year}) {title}.'
        if kw["location"]:
            s += f' {kw["location"]}:'
        if kw["publisher"]:
            s += f' {kw["publisher"]}.'
    elif ref_type == "conference":
        s = f"{authors} ({year}) '{title}', in {kw['conference']}"
        if kw["pages"]:
            s += f', pp. {kw["pages"]}'
        s += '.'
    elif ref_type == "thesis":
        s = f"{authors} ({year}) '{title}', PhD thesis, {kw['institution']}."
    elif ref_type == "website":
        s = f"{authors} ({year}) '{title}' [Online]. Available at: {kw['url']}"
        if kw["accessed"]:
            s += f' (Accessed: {kw["accessed"]}).'
        else:
            s += '.'
    else:  # journal
        s = f"{authors} ({year}) '{title}',"
        if kw["journal"]:
            s += f' {kw["journal"]},'
        if kw["volume"]:
            s += f' {kw["volume"]}'
        if kw["issue"]:
            s += f'({kw["issue"]})'
        s += ','
        if kw["pages"]:
            s += f' pp. {kw["pages"]}.'
        else:
            s = s.rstrip(',') + '.'
    if kw["doi"]:
        s += f' doi: {kw["doi"]}'
    return s


def _fmt_chicago(**kw) -> str:
    """Author. Year. "Title." Journal Volume (Issue): Pages. doi."""
    authors = _join_authors(kw["authors"], "full")
    year = kw["year"]
    title = kw["title"]
    ref_type = kw["ref_type"]

    if ref_type == "book":
        s = f'{authors}. {year}. {title}.'
        if kw["location"]:
            s += f' {kw["location"]}:'
        if kw["publisher"]:
            s += f' {kw["publisher"]}.'
    elif ref_type == "conference":
        s = f'{authors}. {year}. "{title}." Paper presented at {kw["conference"]}.'
    elif ref_type == "thesis":
        s = f'{authors}. {year}. "{title}." PhD dissertation, {kw["institution"]}.'
    elif ref_type == "website":
        s = f'{authors}. {year}. "{title}." {kw["url"]}'
        if kw["accessed"]:
            s += f' (accessed {kw["accessed"]}).'
        else:
            s += '.'
    else:  # journal
        s = f'{authors}. {year}. "{title}."'
        if kw["journal"]:
            s += f' {kw["journal"]}'
        if kw["volume"]:
            s += f' {kw["volume"]}'
        if kw["issue"]:
            s += f' ({kw["issue"]})'
        if kw["pages"]:
            s += f': {kw["pages"]}.'
        else:
            s += '.'
    if kw["doi"]:
        s += f' https://doi.org/{kw["doi"]}.'
    return s


def _fmt_vancouver(**kw) -> str:
    """[N] Author AB. Title. Journal. Year;Vol(Issue):Pages. doi."""
    idx = kw["index"]
    authors = _join_authors(kw["authors"], "last_initials_noperiod")
    year = kw["year"]
    title = kw["title"]
    ref_type = kw["ref_type"]

    if ref_type == "book":
        s = f'[{idx}] {authors}. {title}.'
        if kw["location"]:
            s += f' {kw["location"]}:'
        if kw["publisher"]:
            s += f' {kw["publisher"]};'
        s += f' {year}.'
    elif ref_type == "conference":
        s = f'[{idx}] {authors}. {title}. In: {kw["conference"]}; {year}.'
    elif ref_type == "thesis":
        s = f'[{idx}] {authors}. {title} [PhD dissertation]. {kw["institution"]}; {year}.'
    elif ref_type == "website":
        s = f'[{idx}] {authors}. {title} [Internet]. {kw["url"]}'
        if kw["accessed"]:
            s += f' [cited {kw["accessed"]}].'
        else:
            s += '.'
    else:  # journal
        s = f'[{idx}] {authors}. {title}.'
        if kw["journal"]:
            s += f' {kw["journal"]}.'
        s += f' {year}'
        if kw["volume"]:
            s += f';{kw["volume"]}'
        if kw["issue"]:
            s += f'({kw["issue"]})'
        if kw["pages"]:
            s += f':{kw["pages"]}.'
        else:
            s += '.'
    if kw["doi"]:
        s += f' doi: {kw["doi"]}'
    return s


def _fmt_mla(**kw) -> str:
    """Author. "Title." Journal, vol. X, no. Y, Year, pp. Pages."""
    authors = _join_authors(kw["authors"], "full")
    year = kw["year"]
    title = kw["title"]
    ref_type = kw["ref_type"]

    if ref_type == "book":
        s = f'{authors}. {title}.'
        if kw["publisher"]:
            s += f' {kw["publisher"]},'
        s += f' {year}.'
    elif ref_type == "conference":
        s = f'{authors}. "{title}." {kw["conference"]}, {year}.'
    elif ref_type == "thesis":
        s = f'{authors}. "{title}." {year}, {kw["institution"]}, PhD dissertation.'
    elif ref_type == "website":
        s = f'{authors}. "{title}." {kw["url"]}. Accessed {kw["accessed"]}.' if kw["accessed"] else f'{authors}. "{title}." {kw["url"]}.'
    else:  # journal
        s = f'{authors}. "{title}."'
        if kw["journal"]:
            s += f' {kw["journal"]},'
        if kw["volume"]:
            s += f' vol. {kw["volume"]},'
        if kw["issue"]:
            s += f' no. {kw["issue"]},'
        s += f' {year},'
        if kw["pages"]:
            s += f' pp. {kw["pages"]}.'
        else:
            s = s.rstrip(',') + '.'
    return s


def _fmt_acs(**kw) -> str:
    """[N] Author, A. B.; Author, C. D. Title. Journal Year, Volume, Pages. DOI."""
    idx = kw["index"]
    # ACS uses semicolons between authors
    authors_list = kw["authors"]
    if authors_list:
        authors = "; ".join(authors_list)
    else:
        authors = ""
    year = kw["year"]
    title = kw["title"]
    ref_type = kw["ref_type"]

    if ref_type == "book":
        s = f'[{idx}] {authors}. {title};'
        if kw["publisher"]:
            s += f' {kw["publisher"]}:'
        if kw["location"]:
            s += f' {kw["location"]},'
        s += f' {year}.'
    elif ref_type == "thesis":
        s = f'[{idx}] {authors}. {title}. PhD Dissertation, {kw["institution"]}, {kw["location"]}, {year}.'
    elif ref_type == "website":
        s = f'[{idx}] {authors}. {title}. {kw["url"]} (accessed {kw["accessed"]}).' if kw["accessed"] else f'[{idx}] {authors}. {title}. {kw["url"]}.'
    else:  # journal / conference
        s = f'[{idx}] {authors}. {title}.'
        if kw["journal"]:
            s += f' {kw["journal"]}'
        elif kw["conference"]:
            s += f' {kw["conference"]}'
        s += f' {year}'
        if kw["volume"]:
            s += f', {kw["volume"]}'
        if kw["pages"]:
            s += f', {kw["pages"]}'
        s += '.'
    if kw["doi"]:
        s += f' DOI: {kw["doi"]}.'
    return s
