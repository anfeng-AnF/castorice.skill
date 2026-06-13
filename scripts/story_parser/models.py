from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class SourceRef:
    """Input source identity."""

    value: str
    kind: str
    title: str


@dataclass
class ParsedLine:
    """A normalized line with lightweight semantic tags."""

    text: str
    line_no: int
    kind: str = "text"
    speaker: Optional[str] = None
    choice_kind: Optional[str] = None


@dataclass
class StorySection:
    """A task/story segment, usually starting with a version marker."""

    title: str
    start_line: int
    version: Optional[str] = None
    description: Optional[str] = None
    cast: List[str] = field(default_factory=list)
    lines: List[ParsedLine] = field(default_factory=list)


@dataclass
class DialogueRecord:
    """A dialogue line extracted from normalized story text."""

    source: SourceRef
    line_no: int
    speaker: str
    text: str
    section_title: Optional[str] = None
    version: Optional[str] = None


@dataclass
class ParsedDocument:
    """Full parser result for one source."""

    source: SourceRef
    lines: List[ParsedLine]
    sections: List[StorySection] = field(default_factory=list)
