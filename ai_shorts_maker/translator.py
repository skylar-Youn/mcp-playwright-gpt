"""Translator project repository and utilities."""
from __future__ import annotations

import json
import logging
import glob
import re
import html
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, ValidationError

from .models import ProjectSummary
from .repository import OUTPUT_DIR as SHORTS_OUTPUT_DIR
from .subtitles import parse_subtitle_file, CaptionLine

logger = logging.getLogger(__name__)

TRANSLATOR_DIR = SHORTS_OUTPUT_DIR / "translator_projects"
UPLOADS_DIR = SHORTS_OUTPUT_DIR / "uploads"
DEFAULT_SEGMENT_MAX = 45.0


class TranslatorSegment(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    clip_index: int
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    source_text: Optional[str] = None
    translated_text: Optional[str] = None
    reverse_translated_text: Optional[str] = None
    commentary: Optional[str] = None  # 해설 텍스트 (호환성용)
    commentary_korean: Optional[str] = None  # 해설 한국어
    commentary_japanese: Optional[str] = None  # 해설 일본어
    commentary_reverse_korean: Optional[str] = None  # 해설 역번역 한국어


class TranslatorProject(BaseModel):
    id: str
    base_name: str
    source_video: str
    source_subtitle: Optional[str] = None
    source_origin: Literal["youtube", "upload"] = "youtube"
    target_lang: Literal["ko", "en", "ja"]
    translation_mode: Literal["literal", "adaptive", "reinterpret"] = "adaptive"
    tone_hint: Optional[str] = None
    prompt_hint: Optional[str] = None
    fps: Optional[int] = None
    voice: Optional[str] = None
    voice_synthesis_mode: Literal["subtitle", "commentary", "both"] = "subtitle"  # 음성 합성 대상
    music_track: Optional[str] = None
    duration: Optional[float] = None
    segment_max_duration: float = DEFAULT_SEGMENT_MAX
    status: Literal[
        "draft",
        "segmenting",
        "translating",
        "voice_ready",
        "voice_complete",
        "rendering",
        "rendered",
        "failed",
    ] = "segmenting"
    segments: List[TranslatorSegment] = Field(default_factory=list)
    metadata_path: str
    created_at: datetime
    updated_at: datetime
    extra: Dict[str, Any] = Field(default_factory=dict)

    def completed_steps(self) -> int:
        status_order = {
            "draft": 1,
            "segmenting": 1,
            "translating": 2,
            "voice_ready": 3,
            "voice_complete": 4,
            "rendering": 4,
            "rendered": 5,
            "failed": 1,
        }
        return status_order.get(self.status, 1)


class TranslatorProjectCreate(BaseModel):
    source_video: str
    source_subtitle: Optional[str] = None
    source_origin: Literal["youtube", "upload"] = "youtube"
    target_lang: Literal["ko", "en", "ja"]
    translation_mode: Literal["literal", "adaptive", "reinterpret"] = "adaptive"
    tone_hint: Optional[str] = None
    prompt_hint: Optional[str] = None
    fps: Optional[int] = None
    voice: Optional[str] = None
    music_track: Optional[str] = None
    duration: Optional[float] = None
    segment_max_duration: Optional[float] = None


class TranslatorProjectUpdate(BaseModel):
    status: Optional[TranslatorProject.__fields__["status"].annotation] = None  # type: ignore[valid-type]
    segments: Optional[List[TranslatorSegment]] = None
    tone_hint: Optional[str] = None
    prompt_hint: Optional[str] = None
    voice: Optional[str] = None
    music_track: Optional[str] = None


def ensure_directories() -> None:
    TRANSLATOR_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    _migrate_legacy_backup_directories()


def _migrate_legacy_backup_directories() -> None:
    """Copy legacy backup metadata files into the expected location."""
    try:
        for item in TRANSLATOR_DIR.iterdir():
            if not item.is_dir():
                continue

            legacy_metadata = item / "metadata.json"
            target_path = TRANSLATOR_DIR / f"{item.name}.json"

            if not legacy_metadata.exists():
                continue

            if not target_path.exists():
                try:
                    data = json.loads(legacy_metadata.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    logger.warning("Legacy translator backup %s has invalid metadata", legacy_metadata)
                    continue

                data["metadata_path"] = str(target_path)

                target_path.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2, default=str),
                    encoding="utf-8",
                )

            try:
                legacy_metadata.unlink()
            except OSError as exc:
                logger.warning("Failed to remove legacy metadata file %s: %s", legacy_metadata, exc)
    except OSError as exc:
        logger.warning("Failed to migrate legacy translator backups: %s", exc)


def _project_path(project_id: str) -> Path:
    return TRANSLATOR_DIR / f"{project_id}.json"


def _parse_srt_time(time_str: str) -> float:
    """Parse SRT time format (HH:MM:SS,mmm) to seconds."""
    try:
        time_part, ms_part = time_str.strip().split(',')
        h, m, s = map(int, time_part.split(':'))
        ms = int(ms_part)
        return h * 3600 + m * 60 + s + ms / 1000.0
    except (ValueError, AttributeError):
        return 0.0


def _parse_srt_segments(srt_path: str) -> List[TranslatorSegment]:
    """Parse SRT file and create segments with timing and text."""
    if not Path(srt_path).exists():
        return []

    segments: List[TranslatorSegment] = []
    try:
        content = Path(srt_path).read_text(encoding='utf-8').strip()
        if not content:
            return []

        # Split by double newlines to separate subtitle blocks
        blocks = content.split('\n\n')

        for i, block in enumerate(blocks):
            lines = block.strip().split('\n')
            if len(lines) < 3:
                continue

            # Skip subtitle number (first line)
            timing_line = lines[1]
            text_lines = lines[2:]

            # Parse timing: "00:00:00,160 --> 00:00:05,480"
            if ' --> ' not in timing_line:
                continue

            start_str, end_str = timing_line.split(' --> ')
            start_time = _parse_srt_time(start_str)
            end_time = _parse_srt_time(end_str)

            # Combine text lines
            source_text = ' '.join(text_lines).strip()

            if source_text:  # Only add segments with text
                segments.append(
                    TranslatorSegment(
                        clip_index=i,
                        start=round(start_time, 3),
                        end=round(end_time, 3),
                        source_text=source_text,
                    )
                )
    except Exception as exc:
        logger.warning(f"Failed to parse SRT file {srt_path}: {exc}")

    return segments


def _build_segments(duration: Optional[float], max_length: float, subtitle_path: Optional[str] = None) -> List[TranslatorSegment]:
    # If we have a subtitle file, parse it first
    if subtitle_path and Path(subtitle_path).exists():
        segments = _parse_srt_segments(subtitle_path)
        if segments:  # If we successfully parsed SRT segments
            logger.info(f"Parsed {len(segments)} segments from SRT file: {subtitle_path}")
            return segments

    # Fallback to duration-based segments
    if duration is None or duration <= 0:
        return [TranslatorSegment(clip_index=0, start=0.0, end=float(max_length))]

    segments: List[TranslatorSegment] = []
    start = 0.0
    clip_index = 0
    while start < duration:
        end = min(duration, start + max_length)
        segments.append(
            TranslatorSegment(
                clip_index=clip_index,
                start=round(start, 3),
                end=round(end, 3),
            )
        )
        clip_index += 1
        start = end
    return segments or [TranslatorSegment(clip_index=0, start=0.0, end=float(duration))]


def create_project(payload: TranslatorProjectCreate) -> TranslatorProject:
    ensure_directories()
    project_id = str(uuid4())
    base_name = Path(payload.source_video).stem
    max_duration = payload.segment_max_duration or DEFAULT_SEGMENT_MAX
    segments = _build_segments(payload.duration, max_duration, payload.source_subtitle)

    metadata_path = str(_project_path(project_id))
    project = TranslatorProject(
        id=project_id,
        base_name=base_name,
        source_video=payload.source_video,
        source_subtitle=payload.source_subtitle,
        source_origin=payload.source_origin,
        target_lang=payload.target_lang,
        translation_mode=payload.translation_mode,
        tone_hint=payload.tone_hint,
        prompt_hint=payload.prompt_hint,
        fps=payload.fps,
        voice=payload.voice,
        music_track=payload.music_track,
        duration=payload.duration,
        segment_max_duration=max_duration,
        segments=segments,
        metadata_path=metadata_path,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    return save_project(project)


def save_project(project: TranslatorProject) -> TranslatorProject:
    ensure_directories()
    project.updated_at = datetime.utcnow()
    path = Path(project.metadata_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Save current version
    path.write_text(
        json.dumps(
            project.model_dump(exclude_none=False),
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    # Also save versioned backup for translation comparisons
    _save_translation_version(project)

    return project


def _save_translation_version(project: TranslatorProject) -> None:
    """Save a versioned backup of translation results for comparison."""
    try:
        # Create versions directory
        versions_dir = TRANSLATOR_DIR / "versions" / project.id
        versions_dir.mkdir(parents=True, exist_ok=True)

        # Find next version number
        existing_versions = list(versions_dir.glob("v*.json"))
        if existing_versions:
            version_numbers = []
            for v_file in existing_versions:
                try:
                    version_num = int(v_file.stem[1:])  # Remove 'v' prefix
                    version_numbers.append(version_num)
                except ValueError:
                    continue
            next_version = max(version_numbers) + 1 if version_numbers else 1
        else:
            next_version = 1

        # Save versioned file
        version_file = versions_dir / f"v{next_version}.json"
        version_data = {
            "version": next_version,
            "created_at": project.updated_at.isoformat() if project.updated_at else datetime.utcnow().isoformat(),
            "target_lang": project.target_lang,
            "translation_mode": project.translation_mode,
            "tone_hint": project.tone_hint,
            "segments": [
                {
                    "id": seg.id,
                    "start": seg.start,
                    "end": seg.end,
                    "source_text": seg.source_text,
                    "translated_text": seg.translated_text
                }
                for seg in project.segments
                if seg.translated_text  # Only save segments with translations
            ]
        }

        version_file.write_text(
            json.dumps(version_data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        logger.info(f"Saved translation version {next_version} for project {project.id}")

    except Exception as exc:
        logger.warning(f"Failed to save translation version: {exc}")


def list_translation_versions(project_id: str) -> List[Dict[str, Any]]:
    """List all translation versions for a project."""
    versions_dir = TRANSLATOR_DIR / "versions" / project_id
    if not versions_dir.exists():
        return []

    versions = []
    for version_file in sorted(versions_dir.glob("v*.json")):
        try:
            data = json.loads(version_file.read_text(encoding="utf-8"))
            versions.append({
                "version": data.get("version", 1),
                "created_at": data.get("created_at", ""),
                "target_lang": data.get("target_lang", ""),
                "translation_mode": data.get("translation_mode", ""),
                "tone_hint": data.get("tone_hint", ""),
                "segments_count": len(data.get("segments", []))
            })
        except Exception as exc:
            logger.warning(f"Failed to load version {version_file}: {exc}")

    return versions


def load_translation_version(project_id: str, version: int) -> Optional[Dict[str, Any]]:
    """Load a specific translation version."""
    version_file = TRANSLATOR_DIR / "versions" / project_id / f"v{version}.json"
    if not version_file.exists():
        return None

    try:
        return json.loads(version_file.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning(f"Failed to load version {version}: {exc}")
        return None


def _migrate_project_schema(project_data: Dict[str, Any]) -> Dict[str, Any]:
    """Migrate project data to current schema."""
    # Ensure voice_synthesis_mode exists
    if "voice_synthesis_mode" not in project_data:
        project_data["voice_synthesis_mode"] = "subtitle"

    # Ensure all segments have commentary field
    if "segments" in project_data:
        for segment in project_data["segments"]:
            if "commentary" not in segment:
                segment["commentary"] = None

    return project_data


def load_project(project_id: str) -> TranslatorProject:
    path = _project_path(project_id)
    if not path.exists():
        raise FileNotFoundError(f"Translator project {project_id} not found")
    data = json.loads(path.read_text(encoding="utf-8"))

    # Migrate to current schema
    data = _migrate_project_schema(data)
    try:
        project = TranslatorProject.model_validate(data)
    except ValidationError as exc:  # pragma: no cover
        raise ValueError(f"Invalid translator project data: {exc}") from exc
    return project


def list_projects() -> List[TranslatorProject]:
    ensure_directories()
    projects: List[TranslatorProject] = []
    for file_path in sorted(TRANSLATOR_DIR.glob("*.json")):
        try:
            projects.append(load_project(file_path.stem))
        except (FileNotFoundError, ValueError) as exc:
            logger.warning("Failed to load translator project %s: %s", file_path, exc)
    return projects


def delete_project(project_id: str) -> None:
    path = _project_path(project_id)
    if path.exists():
        try:
            path.unlink()
        except OSError as exc:
            logger.warning("Failed to delete translator project %s: %s", project_id, exc)

    legacy_dir = TRANSLATOR_DIR / project_id
    legacy_metadata = legacy_dir / "metadata.json"
    if legacy_metadata.exists():
        try:
            legacy_metadata.unlink()
        except OSError as exc:
            logger.warning("Failed to remove legacy metadata for %s: %s", project_id, exc)

    if legacy_dir.exists():
        import shutil

        try:
            shutil.rmtree(legacy_dir)
        except OSError as exc:
            logger.warning("Failed to remove translator assets for %s: %s", project_id, exc)

    versions_dir = TRANSLATOR_DIR / "versions" / project_id
    if versions_dir.exists():
        import shutil

        try:
            shutil.rmtree(versions_dir)
        except OSError as exc:
            logger.warning("Failed to remove translator versions for %s: %s", project_id, exc)


def update_project(project_id: str, payload: TranslatorProjectUpdate) -> TranslatorProject:
    project = load_project(project_id)

    if payload.status is not None:
        project.status = payload.status
    if payload.segments is not None:
        # ensure segments sorted by clip_index
        sorted_segments = sorted(payload.segments, key=lambda seg: seg.clip_index)
        project.segments = sorted_segments
    if payload.tone_hint is not None:
        project.tone_hint = payload.tone_hint
    if payload.prompt_hint is not None:
        project.prompt_hint = payload.prompt_hint
    if payload.voice is not None:
        project.voice = payload.voice
    if payload.music_track is not None:
        project.music_track = payload.music_track

    return save_project(project)


def translator_summary(project: TranslatorProject) -> Dict[str, Any]:
    return {
        "id": project.id,
        "title": project.base_name,
        "project_type": "translator",
        "status": project.status,
        "completed_steps": project.completed_steps(),
        "total_steps": 5,
        "thumbnail": project.source_video,
        "updated_at": project.updated_at.isoformat(),
        "language": project.target_lang,
        "topic": project.prompt_hint or project.tone_hint,
        "source_origin": project.source_origin,
    }


def vtt_to_srt(vtt_content: str) -> str:
    """Convert VTT content to SRT format."""
    lines = vtt_content.split('\n')
    srt_lines = []
    subtitle_counter = 1

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Skip WEBVTT header and empty lines
        if line.startswith('WEBVTT') or line == '' or line.startswith('NOTE'):
            i += 1
            continue

        # Check if this is a timestamp line
        if '-->' in line:
            # Convert VTT timestamp to SRT timestamp and remove VTT styling
            timestamp_line = line.replace('.', ',')
            # Remove VTT styling attributes like "align:start position:0%"
            timestamp_parts = timestamp_line.split()
            if len(timestamp_parts) >= 3:  # Should have start --> end
                clean_timestamp = ' '.join(timestamp_parts[:3])  # Keep only "start --> end"
            else:
                clean_timestamp = timestamp_line

            # Add subtitle number
            srt_lines.append(str(subtitle_counter))
            srt_lines.append(clean_timestamp)

            # Get subtitle text (next non-empty lines until empty line or end)
            i += 1
            text_lines = []
            while i < len(lines) and lines[i].strip() != '':
                text = lines[i].strip()
                # Remove VTT formatting tags
                text = re.sub(r'<[^>]*>', '', text)
                # Decode HTML entities
                text = html.unescape(text)
                if text:
                    text_lines.append(text)
                i += 1

            if text_lines:
                srt_lines.extend(text_lines)
                srt_lines.append('')  # Empty line after each subtitle
                subtitle_counter += 1
        else:
            i += 1

    return '\n'.join(srt_lines)


def fix_malformed_srt(srt_path: Path) -> None:
    """Fix malformed SRT files with VTT styling and numbering issues."""
    if not srt_path.exists():
        raise FileNotFoundError(f"SRT file not found: {srt_path}")

    try:
        content = srt_path.read_text(encoding='utf-8')
        lines = [line.strip() for line in content.split('\n')]

        # Extract all subtitle entries
        subtitle_entries = []
        i = 0

        while i < len(lines):
            line = lines[i]

            # Skip empty lines
            if not line:
                i += 1
                continue

            # Look for timestamp lines
            if '-->' in line:
                # Clean timestamp (remove VTT styling)
                timestamp_parts = line.replace('.', ',').split()
                if len(timestamp_parts) >= 3:
                    clean_timestamp = ' '.join(timestamp_parts[:3])
                else:
                    clean_timestamp = line.replace('.', ',')

                # Collect all text lines for this subtitle
                i += 1
                text_lines = []
                while i < len(lines) and lines[i] and '-->' not in lines[i]:
                    text = lines[i]
                    # Skip if it's just a number or duplicate
                    if not text.isdigit() and text not in text_lines:
                        text = html.unescape(text)
                        if text:
                            text_lines.append(text)
                    i += 1

                # Only add if we have text
                if text_lines:
                    subtitle_entries.append({
                        'timestamp': clean_timestamp,
                        'text': text_lines
                    })
            else:
                i += 1

        # Rebuild the SRT file properly
        fixed_lines = []
        for idx, entry in enumerate(subtitle_entries, 1):
            fixed_lines.append(str(idx))
            fixed_lines.append(entry['timestamp'])
            fixed_lines.extend(entry['text'])
            fixed_lines.append('')  # Empty line

        fixed_content = '\n'.join(fixed_lines).strip() + '\n'

        if content != fixed_content:
            srt_path.write_text(fixed_content, encoding='utf-8')
            logger.info(f"Fixed malformed SRT: {srt_path}")

    except Exception as e:
        logger.error(f"Failed to fix malformed SRT: {e}")
        raise


def clean_html_entities_from_srt(srt_path: Path) -> None:
    """Clean HTML entities from existing SRT file."""
    if not srt_path.exists():
        raise FileNotFoundError(f"SRT file not found: {srt_path}")

    try:
        content = srt_path.read_text(encoding='utf-8')
        cleaned_content = html.unescape(content)

        if content != cleaned_content:
            srt_path.write_text(cleaned_content, encoding='utf-8')
            logger.info(f"Cleaned HTML entities from SRT: {srt_path}")

    except Exception as e:
        logger.error(f"Failed to clean HTML entities from SRT: {e}")
        raise


def convert_vtt_to_srt(vtt_path: Path) -> Path:
    """Convert VTT file to SRT format in the same directory."""
    if not vtt_path.exists():
        raise FileNotFoundError(f"VTT file not found: {vtt_path}")

    srt_path = vtt_path.with_suffix('.srt')

    try:
        vtt_content = vtt_path.read_text(encoding='utf-8')
        srt_content = vtt_to_srt(vtt_content)
        srt_path.write_text(srt_content, encoding='utf-8')

        logger.info(f"Converted VTT to SRT: {vtt_path} -> {srt_path}")
        return srt_path

    except Exception as e:
        logger.error(f"Failed to convert VTT to SRT: {e}")
        raise


def downloads_listing(download_dir: Optional[Path] = None) -> List[Dict[str, str]]:
    directory = download_dir or (SHORTS_OUTPUT_DIR.parent.parent / "youtube" / "download")
    directory.mkdir(parents=True, exist_ok=True)

    video_files = list(directory.glob("*.mp4")) + list(directory.glob("*.webm"))
    response: List[Dict[str, str]] = []
    for video in sorted(video_files):
        base = video.stem
        subtitle: Optional[Path] = None

        # First, check if SRT already exists
        escaped_base = glob.escape(base)
        srt_candidates = sorted(list(directory.glob(f"{escaped_base}*.srt")))
        if srt_candidates:
            subtitle = srt_candidates[0]
            # Fix malformed SRT and clean HTML entities
            try:
                fix_malformed_srt(subtitle)
            except Exception as e:
                logger.warning(f"Failed to fix malformed SRT {subtitle}: {e}")
                # Fallback to just cleaning HTML entities
                try:
                    clean_html_entities_from_srt(subtitle)
                except Exception as e2:
                    logger.warning(f"Failed to clean HTML entities from {subtitle}: {e2}")
        else:
            # Look for VTT files and convert them to SRT
            vtt_candidates = sorted(list(directory.glob(f"{escaped_base}*.vtt")))
            if vtt_candidates:
                try:
                    vtt_path = vtt_candidates[0]
                    subtitle = convert_vtt_to_srt(vtt_path)
                except Exception as e:
                    logger.warning(f"Failed to convert VTT to SRT for {vtt_path}: {e}")
                    subtitle = vtt_path  # Fall back to VTT if conversion fails
            else:
                # Look for other subtitle formats
                for ext in (".ass", ".json"):
                    subtitle_candidates = sorted(list(directory.glob(f"{escaped_base}*{ext}")))
                    if subtitle_candidates:
                        subtitle = subtitle_candidates[0]
                        break

        response.append(
            {
                "video_path": str(video),
                "subtitle_path": str(subtitle) if subtitle else "",
                "base_name": base,
            }
        )
    return response


def translate_project_summary(summary: ProjectSummary) -> Dict[str, Any]:
    """Convert Shorts ProjectSummary to dashboard card."""
    thumbnail = summary.video_path or summary.audio_path or summary.base_name
    updated = summary.updated_at.isoformat() if summary.updated_at else None

    audio_ready = bool(summary.audio_path)
    video_ready = bool(summary.video_path)

    if video_ready:
        status = "rendered"
        completed = 5
    elif audio_ready:
        status = "voice_ready"
        completed = 3
    else:
        status = "draft"
        completed = 1

    return {
        "id": summary.base_name,
        "title": summary.topic or summary.base_name,
        "project_type": "shorts",
        "status": status,
        "completed_steps": completed,
        "total_steps": 5,
        "thumbnail": thumbnail,
        "updated_at": updated,
        "language": summary.language,
        "topic": summary.topic,
    }


def aggregate_dashboard_projects(shorts: Iterable[ProjectSummary]) -> List[Dict[str, Any]]:
    translator = [translator_summary(project) for project in list_projects()]
    shorts_cards = [translate_project_summary(item) for item in shorts]
    return translator + shorts_cards


def populate_segments_from_subtitles(project: TranslatorProject) -> TranslatorProject:
    """Load subtitles and populate segment source text."""
    if not project.source_subtitle:
        logger.warning("Project %s has no source subtitle file.", project.id)
        return project

    subtitle_path = Path(project.source_subtitle)
    if not subtitle_path.exists():
        logger.error("Subtitle file not found for project %s: %s", project.id, subtitle_path)
        project.status = "failed"
        project.extra["error"] = f"Subtitle file not found: {subtitle_path.name}"
        return save_project(project)

    captions = parse_subtitle_file(subtitle_path)
    if not captions:
        logger.warning("No captions found in %s", subtitle_path)
        return project

    for segment in project.segments:
        segment_captions = [
            cap.text
            for cap in captions
            if cap.start >= segment.start and cap.end <= segment.end
        ]
        segment.source_text = " ".join(segment_captions).strip()

    logger.info("Populated %d segments with source text for project %s", len(project.segments), project.id)
    return project


def generate_ai_commentary_for_project(project_id: str) -> TranslatorProject:
    """Generate AI commentary for all segments in a project based on source text."""
    project = load_project(project_id)

    if project.status not in ["segmenting", "draft"]:
        logger.warning("Project %s is not in a state for AI commentary generation (status: %s)", project_id, project.status)
        return project

    project = populate_segments_from_subtitles(project)
    if not any(seg.source_text for seg in project.segments):
        project.status = "failed"
        project.extra["error"] = "Could not find any source text to generate commentary from."
        return save_project(project)

    try:
        from .openai_client import OpenAIShortsClient
        client = OpenAIShortsClient()

        # Generate commentary for each segment
        for segment in project.segments:
            if not segment.source_text:
                continue

            # Create prompt for commentary generation
            commentary_prompt = f"""다음은 동영상의 자막 내용입니다. 이 내용에 대해 간단하고 유익한 해설을 한국어로 작성해주세요.

자막 내용: "{segment.source_text}"

해설 요구사항:
- 1-2문장으로 간결하게
- 이해를 돕거나 추가 정보를 제공
- 자연스럽고 친근한 톤
- 시청자에게 도움이 되는 내용

해설:"""

            try:
                commentary = client.generate_script(
                    prompt=commentary_prompt,
                    temperature=0.7
                ).strip()

                segment.commentary = commentary
                logger.info(f"Generated commentary for segment {segment.id}: {commentary[:50]}...")

            except Exception as exc:
                logger.warning(f"Failed to generate commentary for segment {segment.id}: {exc}")
                continue

        project.status = "segmenting"  # Keep in segmenting status
        project = save_project(project)

        logger.info(f"AI commentary generation completed for project {project_id}")
        return project

    except Exception as exc:
        logger.exception("Failed to generate AI commentary for project %s", project_id)
        project.status = "failed"
        project.extra["error"] = f"AI 해설 생성 중 오류 발생: {str(exc)}"
        return save_project(project)


def _find_optimal_commentary_positions(segments: List[TranslatorSegment]) -> List[float]:
    """Find optimal positions to insert commentary between subtitle segments."""
    commentary_positions = []

    for i in range(len(segments) - 1):
        current_segment = segments[i]
        next_segment = segments[i + 1]

        # Calculate gap between current segment end and next segment start
        gap = next_segment.start - current_segment.end

        # If gap is at least 3 seconds, it's suitable for commentary
        if gap >= 3.0:
            # Place commentary in the middle of the gap
            commentary_time = current_segment.end + (gap / 2)
            commentary_positions.append(commentary_time)
        # If gap is between 1.5-3 seconds, place commentary at the end of current segment
        elif gap >= 1.5:
            commentary_time = current_segment.end + 0.5
            commentary_positions.append(commentary_time)
        # For overlapping segments (negative gap), place commentary at the end of current segment
        elif gap < 0:
            # Find a small gap after current segment to insert commentary
            commentary_time = current_segment.end + 0.3
            commentary_positions.append(commentary_time)

    # Add commentary at strategic points (every 15-20 seconds) if no natural gaps found
    if not commentary_positions and segments:
        video_duration = max(seg.end for seg in segments)
        # Add commentary every 18 seconds
        for time_point in [18.0, 36.0, 54.0]:
            if time_point < video_duration - 5.0:  # Don't add too close to end
                commentary_positions.append(time_point)

    # Also consider adding commentary at the very beginning if first segment starts late
    if segments and segments[0].start >= 2.0:
        commentary_positions.insert(0, segments[0].start - 1.0)

    return sorted(commentary_positions)


def _create_commentary_segments(segments: List[TranslatorSegment], commentary_positions: List[float]) -> List[TranslatorSegment]:
    """Create commentary-only segments at specified positions."""
    commentary_segments = []

    for i, position in enumerate(commentary_positions):
        # Commentary segment duration: 2-3 seconds
        start_time = max(0, position)
        end_time = start_time + 2.5

        commentary_segment = TranslatorSegment(
            clip_index=1000 + i,  # Use high index to distinguish commentary segments
            start=round(start_time, 3),
            end=round(end_time, 3),
            source_text=None,  # 원본 자막 (비어있음 - 해설 세그먼트이므로)
            translated_text=None,  # 자막 번역 (비어있음)
            reverse_translated_text=None,  # 자막 역번역 (비어있음)
            commentary_korean=None,  # 해설 한국어
            commentary_japanese=None,  # 해설 일본어 번역
            commentary_reverse_korean=None,  # 해설 역번역 한국어
            commentary=None  # 호환성용
        )
        commentary_segments.append(commentary_segment)

    return commentary_segments


def generate_korean_ai_commentary_for_project(project_id: str) -> TranslatorProject:
    """Generate Korean AI commentary and insert at optimal positions."""
    project = load_project(project_id)

    if project.status not in ["segmenting", "draft", "voice_ready"]:
        logger.warning("Project %s is not in a state for Korean AI commentary generation (status: %s)", project_id, project.status)
        return project

    project = populate_segments_from_subtitles(project)
    if not any(seg.source_text for seg in project.segments):
        project.status = "failed"
        project.extra["error"] = "Could not find any source text to generate commentary from."
        return save_project(project)

    try:
        from .openai_client import OpenAIShortsClient
        client = OpenAIShortsClient()

        # Find optimal positions for commentary insertion
        commentary_positions = _find_optimal_commentary_positions(project.segments)
        logger.info(f"Found {len(commentary_positions)} optimal positions for commentary")

        # Create commentary segments at these positions
        commentary_segments = _create_commentary_segments(project.segments, commentary_positions)

        # Generate AI commentary for each commentary segment
        for i, commentary_segment in enumerate(commentary_segments):
            # Find the surrounding subtitle segments for context
            prev_segments = [seg for seg in project.segments if seg.end <= commentary_segment.start]
            next_segments = [seg for seg in project.segments if seg.start >= commentary_segment.end]

            # Create context from previous segments
            context_texts = []
            if prev_segments:
                # Take last 2 segments for context
                context_segments = prev_segments[-2:] if len(prev_segments) >= 2 else prev_segments
                context_texts = [seg.source_text for seg in context_segments if seg.source_text]

            # Create prompt for Korean commentary generation
            context_str = " ".join(context_texts) if context_texts else "영상 시작"
            korean_commentary_prompt = f"""다음은 드라마/예능 프로그램의 한국어 자막 내용입니다. 이 상황에서 시청자를 위한 재미있고 유용한 해설을 한국어로 작성해주세요.

이전 자막 내용: "{context_str}"

해설 요구사항:
- 한국어로 1문장으로 간결하게 작성 (10-15자 내외)
- 상황을 재미있게 설명하거나 배경 정보 제공
- 시청자의 이해를 돕는 추가 설명
- 드라마틱하고 재미있는 톤 사용
- 이전 내용을 반복하지 말고 새로운 관점 제공

한국어 해설:"""

            try:
                # Generate Korean commentary
                korean_commentary = client.generate_script(
                    prompt=korean_commentary_prompt,
                    temperature=0.8
                ).strip()
                korean_commentary = korean_commentary.strip('"').strip("'")
                commentary_segment.commentary_korean = korean_commentary

                # Generate Japanese translation
                japanese_translation_prompt = f"""다음 한국어 해설을 자연스러운 일본어로 번역해주세요.

한국어 해설: "{korean_commentary}"

일본어 번역:"""

                japanese_translation = client.generate_script(
                    prompt=japanese_translation_prompt,
                    temperature=0.3
                ).strip()
                japanese_translation = japanese_translation.strip('"').strip("'")
                commentary_segment.commentary_japanese = japanese_translation

                # Generate reverse Korean translation
                reverse_korean_prompt = f"""다음 일본어 텍스트를 다시 한국어로 역번역해주세요.

일본어 텍스트: "{japanese_translation}"

한국어 역번역:"""

                reverse_korean = client.generate_script(
                    prompt=reverse_korean_prompt,
                    temperature=0.3
                ).strip()
                reverse_korean = reverse_korean.strip('"').strip("'")
                commentary_segment.commentary_reverse_korean = reverse_korean

                # Keep commentary field for backward compatibility
                commentary_segment.commentary = korean_commentary

                logger.info(f"Generated commentary {i+1} - KR: {korean_commentary}, JP: {japanese_translation}, RV: {reverse_korean}")

            except Exception as exc:
                logger.warning(f"Failed to generate commentary for position {i+1}: {exc}")
                commentary_segment.commentary_korean = "[해설 생성 실패]"
                commentary_segment.commentary_japanese = "[翻訳失敗]"
                commentary_segment.commentary_reverse_korean = "[역번역 실패]"
                commentary_segment.commentary = "[해설 생성 실패]"


        # Merge commentary segments with original segments and sort by time
        all_segments = project.segments + commentary_segments
        all_segments.sort(key=lambda seg: seg.start)

        # Update segment clip_index to maintain order
        for i, segment in enumerate(all_segments):
            segment.clip_index = i

        project.segments = all_segments
        project = save_project(project)
        logger.info(f"Korean AI commentary generation completed for project {project_id}")
        return project

    except Exception as exc:
        logger.exception("Failed to generate Korean AI commentary for project %s", project_id)
        project.status = "failed"
        project.extra["error"] = f"한국어 AI 해설 생성 중 오류 발생: {str(exc)}"
        return save_project(project)


def translate_project_segments(project_id: str) -> TranslatorProject:
    """Run translation for all segments in a project."""
    project = load_project(project_id)

    if project.status not in ["segmenting", "draft"]:
        logger.warning("Project %s is not in a state to be translated (status: %s)", project_id, project.status)
        return project

    project = populate_segments_from_subtitles(project)
    if not any(seg.source_text for seg in project.segments):
        project.status = "failed"
        project.extra["error"] = "Could not find any source text in subtitles to translate."
        return save_project(project)

    project.status = "translating"
    project = save_project(project)

    try:
        from .openai_client import OpenAIShortsClient  # Local import to avoid circular dependency issues

        client = OpenAIShortsClient()

        for segment in project.segments:
            if not segment.source_text:
                continue

            # Remove ">>" prefix from source text for translation
            text_to_translate = segment.source_text.lstrip(">> ").strip()
            if not text_to_translate:
                continue

            translated = client.translate_text(
                text_to_translate=text_to_translate,
                target_lang=project.target_lang,
                translation_mode=project.translation_mode,
                tone_hint=project.tone_hint,
                prompt_hint=project.prompt_hint,
            )
            segment.translated_text = translated

        project.status = "voice_ready"  # Assuming voice is the next step
        project = save_project(project)

        # Save translation results to TXT files
        _save_translation_texts(project)

        return project

    except Exception as e:
        logger.exception("Failed to translate project %s", project_id)
        project.status = "failed"
        project.extra["error"] = str(e)
        return save_project(project)


def translate_text(
    text: str,
    target_lang: str = "ko",
    translation_mode: str = "reinterpret",
    tone_hint: Optional[str] = None,
) -> str:
    """Translate a single text string using the OpenAI client."""
    try:
        from .openai_client import OpenAIShortsClient

        client = OpenAIShortsClient()

        translated = client.translate_text(
            text_to_translate=text,
            target_lang=target_lang,
            translation_mode=translation_mode,
            tone_hint=tone_hint,
            prompt_hint=None,
        )
        return translated

    except Exception as e:
        logger.exception("Failed to translate text: %s", text)
        raise e


def update_segment_text(project_id: str, segment_id: str, text_type: str, text_value: str) -> None:
    """Update a specific text field in a segment."""
    project = load_project(project_id)
    if not project:
        raise FileNotFoundError(f"Project {project_id} not found")

    # Find the segment by ID
    segment = None
    for seg in project.segments:
        if seg.id == segment_id:
            segment = seg
            break

    if not segment:
        raise ValueError(f"Segment {segment_id} not found in project {project_id}")

    # Update the appropriate text field
    if text_type == "source":
        segment.source_text = text_value
    elif text_type == "translated":
        segment.translated_text = text_value
    elif text_type == "reverse_translated":
        segment.reverse_translated_text = text_value
    elif text_type == "commentary":
        segment.commentary = text_value
    else:
        raise ValueError(f"Invalid text_type: {text_type}")

    # Save the updated project
    save_project(project)
    logger.info(f"Updated {text_type} text for segment {segment_id} in project {project_id}")


def update_segment_time(project_id: str, segment_id: str, start_time: float, end_time: float) -> None:
    """Update the timing of a segment."""
    project = load_project(project_id)
    if not project:
        raise FileNotFoundError(f"Project {project_id} not found")

    # Find the segment by ID
    segment = None
    for seg in project.segments:
        if seg.id == segment_id:
            segment = seg
            break

    if not segment:
        raise ValueError(f"Segment {segment_id} not found in project {project_id}")

    # Update the timing
    segment.start = start_time
    segment.end = end_time

    # Save the updated project
    save_project(project)
    logger.info(f"Updated timing for segment {segment_id} in project {project_id}: {start_time:.2f} - {end_time:.2f}")

    # If this is a reverse translation update, re-save the translation texts
    if text_type == "reverse_translated":
        _save_translation_texts(project)


def reorder_project_segments(project_id: str, segment_orders: List[Dict[str, Any]]) -> TranslatorProject:
    """Reorder segments in the project based on the provided order list."""
    project = load_project(project_id)
    if not project:
        raise FileNotFoundError(f"Project {project_id} not found")

    # Create a mapping of segment_id to new_index
    order_map = {order["segment_id"]: order["new_index"] for order in segment_orders}

    # Sort segments by the new index order
    reordered_segments = []
    for order in sorted(segment_orders, key=lambda x: x["new_index"]):
        segment_id = order["segment_id"]
        # Find the segment with this ID
        segment = next((seg for seg in project.segments if seg.id == segment_id), None)
        if segment:
            # Update clip_index to match the new order
            segment.clip_index = order["new_index"]
            reordered_segments.append(segment)

    # Replace the segments list with the reordered one
    project.segments = reordered_segments

    # Save the updated project
    save_project(project)
    logger.info(f"Reordered segments in project {project_id}")

    return project


def reset_project_to_translated(project_id: str) -> TranslatorProject:
    """Reset project status back to translated state to allow editing."""
    project = load_project(project_id)
    if not project:
        raise FileNotFoundError(f"Project {project_id} not found")

    # Reset status to translated state
    project.status = "translated"

    # Save the updated project
    save_project(project)
    logger.info(f"Reset project {project_id} to translated state")

    return project


def _save_translation_texts(project: TranslatorProject) -> None:
    """Save translation results to TXT files."""
    from datetime import datetime

    # Create translation_texts directory
    translation_texts_dir = SHORTS_OUTPUT_DIR / "translation_texts"
    translation_texts_dir.mkdir(exist_ok=True)

    # Create timestamp for filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_filename = f"{project.base_name}_{timestamp}"

    # Collect texts
    korean_texts = []
    japanese_texts = []
    reverse_translated_texts = []

    for segment in project.segments:
        if segment.source_text:
            korean_texts.append(f"[{segment.start:.2f}s-{segment.end:.2f}s] {segment.source_text}")

        if segment.translated_text:
            japanese_texts.append(f"[{segment.start:.2f}s-{segment.end:.2f}s] {segment.translated_text}")

        if segment.reverse_translated_text:
            reverse_translated_texts.append(f"[{segment.start:.2f}s-{segment.end:.2f}s] {segment.reverse_translated_text}")

    # Save Korean original text
    if korean_texts:
        korean_file = translation_texts_dir / f"{base_filename}_korean_original.txt"
        korean_file.write_text('\n'.join(korean_texts), encoding='utf-8')
        logger.info(f"Saved Korean original text to {korean_file}")

    # Save Japanese translation
    if japanese_texts:
        japanese_file = translation_texts_dir / f"{base_filename}_japanese_translation.txt"
        japanese_file.write_text('\n'.join(japanese_texts), encoding='utf-8')
        logger.info(f"Saved Japanese translation to {japanese_file}")

    # Save reverse translated Korean
    if reverse_translated_texts:
        reverse_file = translation_texts_dir / f"{base_filename}_korean_reverse.txt"
        reverse_file.write_text('\n'.join(reverse_translated_texts), encoding='utf-8')
        logger.info(f"Saved reverse translated Korean to {reverse_file}")


def synthesize_voice_for_project(project_id: str) -> TranslatorProject:
    """Generate TTS for the entire translated script."""
    project = load_project(project_id)

    if project.status != "voice_ready":
        logger.warning("Project %s is not ready for voice synthesis (status: %s)", project_id, project.status)
        return project

    # Build script based on voice synthesis mode
    script_parts = []
    for seg in project.segments:
        if project.voice_synthesis_mode == "subtitle" and seg.translated_text:
            script_parts.append(seg.translated_text)
        elif project.voice_synthesis_mode == "commentary" and seg.commentary:
            script_parts.append(seg.commentary)
        elif project.voice_synthesis_mode == "both":
            if seg.translated_text:
                script_parts.append(seg.translated_text)
            if seg.commentary:
                script_parts.append(seg.commentary)

    full_script = "\n".join(script_parts)
    if not full_script:
        project.status = "failed"
        mode_text = {"subtitle": "자막", "commentary": "해설", "both": "자막+해설"}[project.voice_synthesis_mode]
        project.extra["error"] = f"음성 변환할 {mode_text} 텍스트가 없습니다."
        return save_project(project)

    project.status = "rendering" # Next logical status
    project = save_project(project)

    try:
        from .openai_client import OpenAIShortsClient

        client = OpenAIShortsClient()
        output_dir = Path(project.metadata_path).parent
        audio_path = output_dir / f"{project.base_name}_voice.mp3"

        voice = project.voice or "alloy"

        client.synthesize_voice(
            text=full_script,
            voice=voice,
            output_path=audio_path,
        )

        # In a real app, you might want to store this in a more structured way
        project.extra["voice_path"] = str(audio_path)
        project.status = "voice_complete"
        return save_project(project)

    except Exception as e:
        logger.exception("Failed to synthesize voice for project %s", project_id)
        project.status = "failed"
        project.extra["error"] = str(e)
        return save_project(project)


def render_translated_project(project_id: str) -> TranslatorProject:
    """Render the final video for a translated project."""
    project = load_project(project_id)

    if project.status != "voice_complete": # Assuming voice synthesis sets it to this
        logger.warning("Project %s is not ready for rendering (status: %s)", project_id, project.status)
        return project

    try:
        from .media import MediaFactory
        from moviepy.editor import VideoFileClip

        factory = MediaFactory(assets_dir=SHORTS_OUTPUT_DIR.parent / "assets")

        # 1. Load base video
        video_clip = VideoFileClip(project.source_video)

        # 2. Attach new audio
        voice_path = project.extra.get("voice_path")
        if not voice_path or not Path(voice_path).exists():
            raise ValueError("Synthesized voice file not found.")
        
        video_clip, _ = factory.attach_audio(
            video_clip,
            narration_audio=Path(voice_path),
            use_music=False, # TODO: Make this configurable
        )

        # 3. Burn subtitles
        captions = [
            CaptionLine(start=seg.start, end=seg.end, text=seg.translated_text)
            for seg in project.segments
            if seg.translated_text
        ]
        video_clip = factory.burn_subtitles(video_clip, captions)

        # 4. Write to file
        output_dir = Path(project.metadata_path).parent
        output_path = output_dir / f"{project.base_name}_translated.mp4"
        
        video_clip.write_videofile(
            str(output_path),
            codec="libx264",
            audio_codec="aac",
            temp_audiofile=output_dir / "temp-audio.m4a",
            remove_temp=True,
            threads=4, # TODO: Make configurable
            fps=project.fps or 24,
        )

        project.extra["rendered_video_path"] = str(output_path)
        project.status = "rendered"
        return save_project(project)

    except Exception as e:
        logger.exception("Failed to render project %s", project_id)
        project.status = "failed"
        project.extra["error"] = str(e)
        return save_project(project)


def clone_translator_project(project_id: str) -> TranslatorProject:
    """번역기 프로젝트를 복제하여 백업본을 생성합니다."""
    import shutil
    from datetime import datetime

    ensure_directories()

    # 원본 프로젝트 로드
    original_project = load_project(project_id)

    # 새 프로젝트 ID 생성 (백업_원본ID_타임스탬프)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    clone_id = f"backup_{project_id}_{timestamp}"

    # 프로젝트 메타데이터 복제
    cloned_project = TranslatorProject.model_validate(original_project.model_dump())
    cloned_project.id = clone_id
    cloned_project.base_name = f"backup_{original_project.base_name}_{timestamp}"
    cloned_project.created_at = datetime.utcnow()
    cloned_project.updated_at = datetime.utcnow()

    # 자산 보관 디렉터리 생성
    assets_dir = TRANSLATOR_DIR / clone_id
    assets_dir.mkdir(parents=True, exist_ok=True)

    # 표준 위치에 메타데이터 저장되도록 경로 지정
    cloned_project.metadata_path = str(_project_path(clone_id))

    # 파일들 복제 (원본 파일이 존재하는 경우)
    original_video_path = Path(original_project.source_video)
    if original_video_path.exists():
        new_video_path = assets_dir / f"{cloned_project.base_name}{original_video_path.suffix}"
        shutil.copy2(original_video_path, new_video_path)
        cloned_project.source_video = str(new_video_path)

    if original_project.source_subtitle:
        original_subtitle_path = Path(original_project.source_subtitle)
        if original_subtitle_path.exists():
            new_subtitle_path = assets_dir / f"{cloned_project.base_name}{original_subtitle_path.suffix}"
            shutil.copy2(original_subtitle_path, new_subtitle_path)
            cloned_project.source_subtitle = str(new_subtitle_path)

    # 렌더링된 비디오가 있다면 복사
    if "rendered_video_path" in original_project.extra:
        original_rendered_path = Path(original_project.extra["rendered_video_path"])
        if original_rendered_path.exists():
            new_rendered_path = assets_dir / f"{cloned_project.base_name}_translated.mp4"
            shutil.copy2(original_rendered_path, new_rendered_path)
            cloned_project.extra["rendered_video_path"] = str(new_rendered_path)

    # 음성 파일들 복사
    if "audio_files" in original_project.extra:
        cloned_project.extra["audio_files"] = {}
        for key, audio_path in original_project.extra["audio_files"].items():
            if audio_path and Path(audio_path).exists():
                original_audio_path = Path(audio_path)
                new_audio_path = assets_dir / f"{cloned_project.base_name}_{key}{original_audio_path.suffix}"
                shutil.copy2(original_audio_path, new_audio_path)
                cloned_project.extra["audio_files"][key] = str(new_audio_path)

    # 복제된 프로젝트 저장
    return save_project(cloned_project)


__all__ = [
    "TranslatorSegment",
    "TranslatorProject",
    "TranslatorProjectCreate",
    "TranslatorProjectUpdate",
    "create_project",
    "save_project",
    "load_project",
    "list_projects",
    "delete_project",
    "update_project",
    "clone_translator_project",
    "downloads_listing",
    "aggregate_dashboard_projects",
    "generate_ai_commentary_for_project",
    "generate_korean_ai_commentary_for_project",
    "translate_project_segments",
    "synthesize_voice_for_project",
    "render_translated_project",
    "vtt_to_srt",
    "convert_vtt_to_srt",
    "fix_malformed_srt",
    "clean_html_entities_from_srt",
    "UPLOADS_DIR",
    "ensure_directories",
]
