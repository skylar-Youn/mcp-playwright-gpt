"""Translator project repository and utilities."""
from __future__ import annotations

import json
import logging
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


def _project_path(project_id: str) -> Path:
    return TRANSLATOR_DIR / f"{project_id}.json"


def _build_segments(duration: Optional[float], max_length: float) -> List[TranslatorSegment]:
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
    segments = _build_segments(payload.duration, max_duration)

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
    path.write_text(
        json.dumps(
            project.model_dump(exclude_none=False),
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    return project


def load_project(project_id: str) -> TranslatorProject:
    path = _project_path(project_id)
    if not path.exists():
        raise FileNotFoundError(f"Translator project {project_id} not found")
    data = json.loads(path.read_text(encoding="utf-8"))
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


def downloads_listing(download_dir: Optional[Path] = None) -> List[Dict[str, str]]:
    directory = download_dir or (SHORTS_OUTPUT_DIR.parent / "youtube" / "download")
    directory.mkdir(parents=True, exist_ok=True)

    video_files = list(directory.glob("*.mp4"))
    response: List[Dict[str, str]] = []
    for video in sorted(video_files):
        base = video.stem
        subtitle: Optional[Path] = None
        for ext in (".srt", ".vtt", ".ass", ".json"):
            candidate = video.with_suffix(ext)
            if candidate.exists():
                subtitle = candidate
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

            translated = client.translate_text(
                text_to_translate=segment.source_text,
                target_lang=project.target_lang,
                translation_mode=project.translation_mode,
                tone_hint=project.tone_hint,
                prompt_hint=project.prompt_hint,
            )
            segment.translated_text = translated

        project.status = "voice_ready"  # Assuming voice is the next step
        return save_project(project)

    except Exception as e:
        logger.exception("Failed to translate project %s", project_id)
        project.status = "failed"
        project.extra["error"] = str(e)
        return save_project(project)


def synthesize_voice_for_project(project_id: str) -> TranslatorProject:
    """Generate TTS for the entire translated script."""
    project = load_project(project_id)

    if project.status != "voice_ready":
        logger.warning("Project %s is not ready for voice synthesis (status: %s)", project_id, project.status)
        return project

    full_script = "\n".join([seg.translated_text for seg in project.segments if seg.translated_text])
    if not full_script:
        project.status = "failed"
        project.extra["error"] = "No translated text available to synthesize."
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
    "downloads_listing",
    "aggregate_dashboard_projects",
    "translate_project_segments",
    "synthesize_voice_for_project",
    "render_translated_project",
    "UPLOADS_DIR",
    "ensure_directories",
]
