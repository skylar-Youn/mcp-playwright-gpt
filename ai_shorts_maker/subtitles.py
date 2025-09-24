"""Subtitle helpers."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator, List
from uuid import uuid4

from .models import SubtitleLine

@dataclass
class CaptionLine:
    start: float
    end: float
    text: str

    def to_srt_block(self, index: int) -> str:
        return f"{index}\n{format_timestamp(self.start)} --> {format_timestamp(self.end)}\n{self.text}\n"


def split_script_into_sentences(script: str) -> List[str]:
    """Split the generated script into sentences."""
    cleaned = script.strip().replace("\r", "")
    sentences = re.split(r"(?<=[.!?])\s+|\n+", cleaned)
    sentences = [s.strip() for s in sentences if s.strip()]
    return sentences or [cleaned]


def allocate_caption_timings(sentences: List[str], total_duration: float) -> List[CaptionLine]:
    """Allocate caption durations proportional to sentence length."""
    if not sentences:
        return []

    total_chars = sum(len(s) for s in sentences)
    if total_chars == 0:
        share = total_duration / len(sentences)
        return [CaptionLine(i * share, (i + 1) * share, sentences[i]) for i in range(len(sentences))]

    captions: List[CaptionLine] = []
    cursor = 0.0
    for sentence in sentences:
        ratio = len(sentence) / total_chars
        duration = max(total_duration * ratio, 1.2)
        start = cursor
        end = min(cursor + duration, total_duration)
        captions.append(CaptionLine(start=start, end=end, text=sentence))
        cursor = end

    if captions:
        captions[-1].end = total_duration
    return captions


def captions_to_srt(captions: Iterable[CaptionLine]) -> str:
    blocks = [caption.to_srt_block(idx + 1) for idx, caption in enumerate(captions)]
    return "\n".join(blocks)


def write_srt_file(captions: Iterable[CaptionLine], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(captions_to_srt(captions), encoding="utf-8")
    return output_path


def subtitle_lines_from_captions(captions: List[CaptionLine]) -> List[SubtitleLine]:
    """Convert CaptionLine objects into metadata subtitle lines with generated IDs."""

    now = datetime.utcnow()
    return [
        SubtitleLine(
            id=str(uuid4()),
            start=caption.start,
            end=caption.end,
            text=caption.text,
            created_at=now,
            updated_at=now,
        )
        for caption in captions
    ]


def captions_from_subtitle_lines(subs: Iterable[SubtitleLine]) -> Iterator[CaptionLine]:
    for sub in subs:
        yield CaptionLine(start=sub.start, end=sub.end, text=sub.text)


def write_srt_from_subtitles(subtitles: Iterable[SubtitleLine], output_path: Path) -> Path:
    return write_srt_file(captions_from_subtitle_lines(subtitles), output_path)


def format_timestamp(seconds: float) -> str:
    millis = int(round(seconds * 1000))
    hours, remainder = divmod(millis, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _parse_timestamp(ts: str) -> float:
    ts = ts.replace(".", ",")
    parts = ts.split(",")
    if len(parts) != 2:
        time_parts = list(map(int, ts.split(":")))
        h, m, s = time_parts[-3:]
        ms = 0
    else:
        time_str, ms_str = parts
        time_parts = list(map(int, time_str.split(":")))
        h, m, s = time_parts[-3:]
        ms = int(ms_str)

    return h * 3600 + m * 60 + s + ms / 1000.0


TIMECODE_RE = re.compile(r"(\d{1,2}:)?\d{1,2}:\d{1,2}[,.]\d{1,3}\s+-->\s+(\d{1,2}:)?\d{1,2}:\d{1,2}[,.]\d{1,3}")


def parse_subtitle_file(path: Path) -> List[CaptionLine]:
    if not path.exists():
        return []

    text = path.read_text(encoding="utf-8", errors="ignore").strip()
    lines = text.splitlines()
    captions: List[CaptionLine] = []
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue

        if TIMECODE_RE.match(line):
            try:
                start_str, end_str = [p.strip() for p in line.split("-->")]
                start = _parse_timestamp(start_str)
                end = _parse_timestamp(end_str)

                i += 1
                text_block = []
                while i < len(lines) and lines[i].strip():
                    text_block.append(lines[i].strip())
                    i += 1
                
                if text_block:
                    captions.append(CaptionLine(start=start, end=end, text="\n".join(text_block)))
            except (ValueError, IndexError):
                # Ignore malformed timecode lines
                i += 1
        else:
            i += 1
            
    return captions
