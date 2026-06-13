from __future__ import annotations

import html
import re
from typing import Iterable, List, Optional, Set, Tuple

from .models import ParsedLine


DROP_LINE_PATTERNS = [
    re.compile(r"^\s*$"),
    re.compile(r"^编辑$"),
    re.compile(r"^折叠$"),
    re.compile(r"^展开$"),
    re.compile(r"^收起$"),
    re.compile(r"^返回顶部$"),
    re.compile(r"^目录$"),
    re.compile(r"^更多$"),
    re.compile(r".*\.(?:png|jpg|jpeg|gif|webp|svg)$", re.IGNORECASE),
]

INLINE_NOISE_PATTERNS = [
    (re.compile(r"[\w\-\u4e00-\u9fff]+头像(?:-\d+)?\.(?:png|jpg|jpeg|gif|webp)", re.IGNORECASE), ""),
    (re.compile(r"图标-位置\.(?:png|jpg|jpeg|gif|webp)", re.IGNORECASE), ""),
    (re.compile(r"短信-警告\.(?:png|jpg|jpeg|gif|webp)", re.IGNORECASE), ""),
]

CHOICE_RE = re.compile(r"^剧情选项-图标-([^.\s]+)\.png\s*(.*)$")
META_PREFIXES = ("所属版本", "任务描述", "出场人物")
HEADINGS = {"剧情内容", "剧情梗概", "过场动画"}
DEFAULT_SPEAKER_HINTS = {
    "开拓者",
    "星",
    "穹",
    "帕姆",
    "姬子",
    "瓦尔特",
    "丹恒",
    "三月七",
    "黑天鹅",
    "星期日",
    "白厄",
    "缇宝",
    "万敌",
    "遐蝶",
    "阿格莱雅",
    "那刻夏",
    "风堇",
    "赛飞儿",
    "黄泉",
    "卡芙卡",
    "流萤",
}


def normalize_text(raw_text: str, speaker_hints: Optional[Iterable[str]] = None) -> list[ParsedLine]:
    """Normalize copied page text into typed lines."""

    raw_text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    raw_text = html.unescape(raw_text)
    raw_text = raw_text.replace("\u00a0", " ").replace("\u3000", " ")

    pairs: list[tuple[int, str]] = []
    previous = ""
    for line_no, raw_line in enumerate(raw_text.split("\n"), 1):
        line = clean_line(raw_line)
        if should_drop_line(line):
            continue
        if line == previous:
            continue
        pairs.append((line_no, line))
        previous = line

    hints = collect_speaker_hints(pairs, speaker_hints)
    repaired = repair_speaker_pairs(pairs, hints)
    return [classify_line(line_no, line) for line_no, line in repaired]


def clean_line(raw_line: str) -> str:
    line = raw_line.strip()
    for pattern, replacement in INLINE_NOISE_PATTERNS:
        line = pattern.sub(replacement, line)
    line = normalize_choice_markup(line)
    line = re.sub(r"[ \t]+", " ", line)
    return line.strip()


def normalize_choice_markup(line: str) -> str:
    match = CHOICE_RE.match(line)
    if not match:
        return line
    kind = match.group(1).strip()
    text = match.group(2).strip()
    return f"[choice:{kind}] {text}" if text else f"[choice:{kind}]"


def should_drop_line(line: str) -> bool:
    if not line:
        return True
    return any(pattern.match(line) for pattern in DROP_LINE_PATTERNS)


def collect_speaker_hints(
    pairs: list[tuple[int, str]],
    extra_hints: Optional[Iterable[str]] = None,
) -> Set[str]:
    hints = set(DEFAULT_SPEAKER_HINTS)
    if extra_hints:
        hints.update(hint.strip() for hint in extra_hints if hint.strip())

    for _, line in pairs:
        if line.startswith("出场人物"):
            value = line.removeprefix("出场人物").strip()
            hints.update(name for name in re.split(r"\s+", value) if name)
            continue

        speaker = parse_speaker(line)
        if speaker:
            hints.add(speaker[0])

    return hints


def repair_speaker_pairs(pairs: list[tuple[int, str]], speaker_hints: Set[str]) -> list[tuple[int, str]]:
    """Repair simple web-copy blocks like `Speaker` then `line`."""

    repaired: list[tuple[int, str]] = []
    index = 0
    while index < len(pairs):
        line_no, line = pairs[index]
        if (
            is_standalone_speaker(line, speaker_hints)
            and index + 1 < len(pairs)
            and is_dialogue_payload(pairs[index + 1][1], speaker_hints)
        ):
            next_line_no, next_line = pairs[index + 1]
            repaired.append((line_no, f"{line}：{next_line}"))
            index += 2
            continue

        repaired.append((line_no, line))
        index += 1

    return repaired


def is_standalone_speaker(line: str, speaker_hints: Set[str]) -> bool:
    if line not in speaker_hints:
        return False
    if line in HEADINGS:
        return False
    if line.startswith(META_PREFIXES):
        return False
    if line.startswith("[choice:"):
        return False
    if "：" in line or ":" in line:
        return False
    if len(line) > 16:
        return False
    if line.endswith(("。", "！", "？", "…", "」", "）")):
        return False
    if re.search(r"[，。？！；：、]", line):
        return False
    return bool(re.search(r"[\u4e00-\u9fffA-Za-z]", line))


def is_dialogue_payload(line: str, speaker_hints: Set[str]) -> bool:
    if not line:
        return False
    if line.startswith("[choice:"):
        return False
    if line in HEADINGS:
        return False
    if line.startswith(META_PREFIXES):
        return False
    if is_standalone_speaker(line, speaker_hints):
        return False
    return True


def classify_line(line_no: int, line: str) -> ParsedLine:
    choice = parse_choice(line)
    if choice:
        kind, text = choice
        return ParsedLine(text=text, line_no=line_no, kind="choice", choice_kind=kind)

    speaker = parse_speaker(line)
    if speaker:
        name, text = speaker
        return ParsedLine(text=text, line_no=line_no, kind="dialogue", speaker=name)

    if line.startswith(META_PREFIXES):
        return ParsedLine(text=line, line_no=line_no, kind="meta")

    if line in HEADINGS or line.startswith("额外对话"):
        return ParsedLine(text=line, line_no=line_no, kind="heading")

    return ParsedLine(text=line, line_no=line_no, kind="text")


def parse_choice(line: str) -> Optional[Tuple[str, str]]:
    match = re.match(r"^\[choice:([^\]]+)\]\s*(.*)$", line)
    if not match:
        return None
    return match.group(1).strip(), match.group(2).strip()


def parse_speaker(line: str) -> Optional[Tuple[str, str]]:
    match = re.match(r"^([^:：]{1,32})[:：]\s*(.+)$", line)
    if not match:
        return None
    speaker = match.group(1).strip()
    text = match.group(2).strip()
    if not speaker or not text:
        return None
    if "\n" in speaker:
        return None
    if speaker.startswith("[choice"):
        return None
    return speaker, text


def lines_to_text(lines: Iterable[ParsedLine]) -> str:
    rendered: List[str] = []
    for line in lines:
        if line.kind == "dialogue" and line.speaker:
            rendered.append(f"{line.speaker}：{line.text}")
        elif line.kind == "choice":
            rendered.append(f"[choice:{line.choice_kind}] {line.text}".rstrip())
        else:
            rendered.append(line.text)
    return "\n".join(rendered).strip() + "\n"
