from dataclasses import asdict, dataclass, field
from typing import Optional


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
    citations: Optional[int] = None
    is_open_access: Optional[bool] = None
    type: Optional[str] = None
    publisher: Optional[str] = None

    def dedup_key(self) -> str:
        if self.doi:
            normalized = self.doi.strip().lower()
            normalized = normalized.removeprefix("https://doi.org/").removeprefix("http://doi.org/")
            return f"doi:{normalized}"
        return f"{self.source}:{self.source_id}"

    def to_dict(self) -> dict:
        return asdict(self)
