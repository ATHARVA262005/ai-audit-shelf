"""Data models for the AI Audit system."""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, List


@dataclass
class Chapter:
    id: str
    prompt: str
    result: str
    actor: str
    timestamp: str
    source: str = "manual"
    model: Optional[str] = None
    temperature: Optional[float] = None
    seed: Optional[int] = None
    validation_status: Optional[str] = None  # e.g., "passed", "failed", "skipped"
    validation_message: Optional[str] = None  # details of validation rule run
    hallucination_score: Optional[float] = None  # 0.0 (hallucinated) to 1.0 (100% faithful)
    hallucinated_claims: list = field(default_factory=list)  # list of flagged sentences
    metadata: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Chapter":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class Book:
    id: str
    title: str
    chapter_ids: list[str]
    version: int
    feature: str
    created_at: str
    parent_book_id: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Book":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
