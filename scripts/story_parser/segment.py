from __future__ import annotations

import re
from typing import Iterable, Optional, Sequence

from .models import DialogueRecord, ParsedDocument, ParsedLine, SourceRef, StorySection


def build_sections(lines: Sequence[ParsedLine]) -> list[StorySection]:
    """Split normalized lines into task sections."""

    sections: list[StorySection] = []
    current: Optional[StorySection] = None

    for line in lines:
        version = parse_version(line.text)
        if version is not None:
            current = StorySection(
                title=f"Version {version} section {len(sections) + 1}",
                start_line=line.line_no,
                version=version,
            )
            current.lines.append(line)
            sections.append(current)
            continue

        if current is None:
            current = StorySection(
                title=f"Prelude section {len(sections) + 1}",
                start_line=line.line_no,
            )
            sections.append(current)

        if line.text.startswith("任务描述"):
            current.description = line.text.removeprefix("任务描述").strip()
        elif line.text.startswith("出场人物"):
            current.cast = parse_cast(line.text)
        elif line.kind == "heading" and current.title.startswith("Version"):
            # Use the first meaningful heading as a friendlier title.
            if not line.text.startswith("额外对话"):
                current.title = line.text

        current.lines.append(line)

    return sections


def parse_version(text: str) -> Optional[str]:
    match = re.match(r"^所属版本\s+(.+)$", text)
    return match.group(1).strip() if match else None


def parse_cast(text: str) -> list[str]:
    value = text.removeprefix("出场人物").strip()
    if not value:
        return []
    names = [name.strip() for name in re.split(r"\s+", value) if name.strip()]

    deduped: list[str] = []
    seen: set[str] = set()
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        deduped.append(name)
    return deduped


def section_for_line(sections: Sequence[StorySection], line_no: int) -> Optional[StorySection]:
    chosen: Optional[StorySection] = None
    for section in sections:
        if section.start_line <= line_no:
            chosen = section
        else:
            break
    return chosen


def extract_dialogue(
    document: ParsedDocument,
    speakers: Optional[Iterable[str]] = None,
) -> list[DialogueRecord]:
    """Extract dialogue records, optionally limited to target speakers."""

    speaker_set = {speaker.strip() for speaker in speakers or [] if speaker.strip()}
    records: list[DialogueRecord] = []

    for line in document.lines:
        if line.kind != "dialogue" or not line.speaker:
            continue
        if speaker_set and line.speaker not in speaker_set:
            continue

        section = section_for_line(document.sections, line.line_no)
        records.append(
            DialogueRecord(
                source=document.source,
                line_no=line.line_no,
                speaker=line.speaker,
                text=line.text,
                section_title=section.title if section else None,
                version=section.version if section else None,
            )
        )

    return records


def make_document(source: SourceRef, lines: list[ParsedLine]) -> ParsedDocument:
    document = ParsedDocument(source=source, lines=lines)
    document.sections = build_sections(lines)
    return document
