"""Service layer for project editing operations."""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

import moviepy

try:  # moviepy >=2 제거 대비
    from moviepy.editor import ColorClip, VideoFileClip, CompositeVideoClip, concatenate_videoclips
except ModuleNotFoundError:  # pragma: no cover
    from moviepy import ColorClip, VideoFileClip, CompositeVideoClip, concatenate_videoclips  # type: ignore

try:
    from moviepy.editor import ImageClip
except ModuleNotFoundError:  # pragma: no cover
    from moviepy import ImageClip  # type: ignore

USE_WITH_DURATION = hasattr(ImageClip, "with_duration")
USE_WITH_POSITION = hasattr(ImageClip, "with_position")


def _with_position(clip, position):
    if position is None:
        return clip
    if USE_WITH_POSITION and hasattr(clip, "with_position"):
        return clip.with_position(position)
    if hasattr(clip, "set_position"):
        return clip.set_position(position)
    clip.pos = position
    return clip


def _with_start(clip, start):
    if hasattr(clip, "with_start"):
        return clip.with_start(start)
    if hasattr(clip, "set_start"):
        return clip.set_start(start)
    clip.start = start
    clip.end = (clip.end if getattr(clip, "end", None) is not None else 0) + start
    return clip


def _with_end(clip, end):
    if hasattr(clip, "with_end"):
        return clip.with_end(end)
    if hasattr(clip, "set_end"):
        return clip.set_end(end)
    clip.end = end
    clip.duration = end - getattr(clip, "start", 0)
    return clip

from .media import MediaFactory, _resize_clip, _set_duration, _set_fps, _video_loop
from .models import (
    ProjectMetadata,
    ProjectVersionInfo,
    SubtitleCreate,
    SubtitleLine,
    SubtitleUpdate,
    TimelineSegment,
    TimelineUpdate,
)
from .repository import (
    delete_project,
    list_versions as repository_list_versions,
    load_project,
    load_project_version,
    save_project,
)
from .subtitles import captions_from_subtitle_lines, write_srt_from_subtitles

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
OUTPUT_DIR = Path(__file__).resolve().parent / "outputs"


def _touch(metadata: ProjectMetadata) -> None:
    metadata.version += 1
    metadata.updated_at = datetime.utcnow()


def add_subtitle(base_name: str, payload: SubtitleCreate) -> ProjectMetadata:
    metadata = load_project(base_name)
    new_line = SubtitleLine(
        id=str(uuid4()),
        start=payload.start,
        end=payload.end,
        text=payload.text,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    metadata.captions.append(new_line)
    metadata.captions.sort(key=lambda s: s.start)
    _touch(metadata)
    return save_project(metadata)


def update_subtitle(base_name: str, subtitle_id: str, payload: SubtitleUpdate) -> ProjectMetadata:
    metadata = load_project(base_name)
    target = next((sub for sub in metadata.captions if sub.id == subtitle_id), None)
    if target is None:
        raise KeyError(f"Subtitle {subtitle_id} not found")

    if payload.start is not None:
        target.start = payload.start
    if payload.end is not None:
        target.end = payload.end
    if payload.text is not None:
        target.text = payload.text
    target.updated_at = datetime.utcnow()
    metadata.captions.sort(key=lambda s: s.start)
    _touch(metadata)
    return save_project(metadata)


def delete_subtitle_line(base_name: str, subtitle_id: str) -> ProjectMetadata:
    metadata = load_project(base_name)
    before = len(metadata.captions)
    metadata.captions = [sub for sub in metadata.captions if sub.id != subtitle_id]
    if len(metadata.captions) == before:
        raise KeyError(f"Subtitle {subtitle_id} not found")
    _touch(metadata)
    return save_project(metadata)


def replace_timeline(base_name: str, payload: TimelineUpdate) -> ProjectMetadata:
    metadata = load_project(base_name)
    metadata.timeline = payload.segments
    _touch(metadata)
    return save_project(metadata)


def update_audio_settings(
    base_name: str,
    *,
    music_enabled: Optional[bool] = None,
    music_volume: Optional[float] = None,
    ducking: Optional[float] = None,
    music_track: Optional[str] = None,
) -> ProjectMetadata:
    metadata = load_project(base_name)
    settings = metadata.audio_settings
    if music_enabled is not None:
        settings.music_enabled = music_enabled
    if music_volume is not None:
        settings.music_volume = music_volume
    if ducking is not None:
        settings.ducking = ducking
    if music_track is not None:
        settings.music_track = music_track
    _touch(metadata)
    return save_project(metadata)


def _resolve_media_path(source: Optional[str]) -> Optional[Path]:
    if not source or source == "auto":
        return None
    candidate = Path(source)
    if candidate.exists():
        return candidate
    for root in (
        OUTPUT_DIR,
        ASSETS_DIR,
        ASSETS_DIR / "broll",
        ASSETS_DIR / "music",
    ):
        maybe = root / source
        if maybe.exists():
            return maybe
    return None


def _is_overlay(segment: TimelineSegment) -> bool:
    if segment.media_type in {"image", "overlay", "image_overlay"}:
        return True
    return bool(segment.extras.get("overlay"))


def _segment_to_clip(
    segment: TimelineSegment,
    factory: MediaFactory,
    fps: int,
    fallback_color: tuple[int, int, int] = (15, 15, 20),
) -> VideoFileClip:
    duration = max(segment.end - segment.start, 0.1)
    path = _resolve_media_path(segment.source)

    clip = None
    if path:
        try:
            if path.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"}:
                clip = VideoFileClip(str(path))
            elif path.suffix.lower() in {".jpg", ".jpeg", ".png"}:
                clip = ImageClip(str(path))
        except OSError:
            clip = None

    if clip is None:
        clip = ColorClip(size=factory.canvas_size, color=fallback_color, duration=duration)

    clip = _resize_clip(clip, factory.canvas_size)
    clip = _set_fps(clip, fps)

    clip_duration = getattr(clip, "duration", None)
    if clip_duration is None:
        if USE_WITH_DURATION and hasattr(clip, "with_duration"):
            clip = clip.with_duration(duration)
        else:
            clip = _set_duration(clip, duration)
    elif clip_duration > duration + 0.02:
        clip = clip.subclip(0, duration)
    elif clip_duration < duration - 0.02:
        clip = _video_loop(clip, duration=duration)

    clip = _set_duration(clip, duration)

    # Position handling (overlay clips support extras.position)
    position = segment.extras.get("position") if isinstance(segment.extras, dict) else None
    if position is not None:
        if isinstance(position, (list, tuple)):
            clip = _with_position(clip, tuple(position))
        else:
            clip = _with_position(clip, position)
    elif _is_overlay(segment):
        clip = _with_position(clip, "center")

    return clip


def _gap_clip(gap: float, factory: MediaFactory, fps: int) -> VideoFileClip:
    filler = ColorClip(size=factory.canvas_size, color=(10, 12, 18), duration=gap)
    filler = _resize_clip(filler, factory.canvas_size)
    filler = _set_fps(filler, fps)
    return _set_duration(filler, gap)


def render_project(base_name: str, *, burn_subs: bool = False) -> ProjectMetadata:
    metadata = load_project(base_name)
    timeline_segments = sorted(metadata.timeline, key=lambda seg: seg.start)

    base_duration = metadata.duration
    if base_duration is None and timeline_segments:
        base_duration = max(seg.end for seg in timeline_segments)
    if base_duration is None and metadata.captions:
        base_duration = max(sub.end for sub in metadata.captions)
    if base_duration is None:
        base_duration = 1.0

    fps_candidates: List[int] = []
    for seg in timeline_segments:
        if isinstance(seg.extras, dict) and "fps" in seg.extras:
            try:
                fps_candidates.append(int(seg.extras["fps"]))
            except (TypeError, ValueError):
                continue
    if metadata.extra and isinstance(metadata.extra, dict):
        fps_hint = metadata.extra.get("fps")
        if isinstance(fps_hint, (int, float)):
            fps_candidates.append(int(fps_hint))
    fps = fps_candidates[0] if fps_candidates else 24

    factory = MediaFactory(ASSETS_DIR, fps=fps)

    base_segments = [seg for seg in timeline_segments if not _is_overlay(seg)]
    overlay_segments = [seg for seg in timeline_segments if _is_overlay(seg)]

    clips: List[VideoFileClip] = []
    clip_pool: List[VideoFileClip] = []
    cursor = 0.0
    for segment in base_segments:
        seg_duration = max(segment.end - segment.start, 0.0)
        if seg_duration <= 0:
            continue
        if segment.start > cursor + 1e-3:
            gap = segment.start - cursor
            filler = _gap_clip(gap, factory, fps)
            clips.append(filler)
            clip_pool.append(filler)
            cursor += gap

        clip = _segment_to_clip(segment, factory, fps)
        clips.append(clip)
        clip_pool.append(clip)
        cursor = max(cursor, segment.end)

    if cursor < base_duration - 1e-3:
        filler = _gap_clip(base_duration - cursor, factory, fps)
        clips.append(filler)
        clip_pool.append(filler)

    if clips:
        timeline_clip = concatenate_videoclips(clips, method="compose")
    else:
        timeline_clip = ColorClip(size=factory.canvas_size, color=(15, 15, 20), duration=base_duration)
        timeline_clip = _set_fps(timeline_clip, fps)

    timeline_clip = _set_duration(timeline_clip, base_duration)

    overlay_clips: List[VideoFileClip] = []
    for segment in overlay_segments:
        seg_duration = max(segment.end - segment.start, 0.0)
        if seg_duration <= 0:
            continue
        clip = _segment_to_clip(segment, factory, fps)
        clip = _with_start(clip, segment.start)
        clip = _with_end(clip, segment.end)
        overlay_clips.append(clip)
        clip_pool.append(clip)

    voice_path = metadata.audio_settings.voice_path or metadata.audio_path
    if not voice_path:
        timeline_clip.close()
        raise RuntimeError("Voice audio path is not defined in metadata")

    music_override = None
    if metadata.audio_settings.music_track:
        music_override = _resolve_media_path(metadata.audio_settings.music_track)

    clip_with_audio = None
    render_clip = None
    composite_clip = None
    try:
        visual_clip = timeline_clip
        if overlay_clips:
            composite_clip = CompositeVideoClip([timeline_clip, *overlay_clips], size=factory.canvas_size)
            visual_clip = composite_clip

        clip_with_audio, selected_music = factory.attach_audio(
            visual_clip,
            Path(voice_path),
            music_volume=metadata.audio_settings.music_volume,
            ducking=metadata.audio_settings.ducking,
            use_music=metadata.audio_settings.music_enabled,
            music_path=music_override,
        )

        subtitles_iter = list(captions_from_subtitle_lines(metadata.captions))
        render_clip = (
            factory.burn_subtitles(clip_with_audio, subtitles_iter) if burn_subs else clip_with_audio
        )

        timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        video_filename = f"{metadata.base_name}-render-{timestamp}.mp4"
        output_dir = Path(metadata.video_path).parent if metadata.video_path else OUTPUT_DIR
        output_dir.mkdir(parents=True, exist_ok=True)
        video_path = output_dir / video_filename

        render_clip.write_videofile(
            str(video_path),
            fps=fps,
            codec="libx264",
            audio_codec="aac",
            temp_audiofile=str(output_dir / f"{metadata.base_name}_temp_audio.m4a"),
            remove_temp=True,
            threads=os.cpu_count() or 4,
        )

        metadata.video_path = str(video_path)
        metadata.duration = render_clip.duration or base_duration
        metadata.audio_settings.music_track = (
            str(selected_music) if selected_music else metadata.audio_settings.music_track
        )
        write_srt_from_subtitles(metadata.captions, Path(metadata.subtitles_path))
        _touch(metadata)
        return save_project(metadata)
    finally:
        if render_clip is not None:
            try:
                render_clip.close()
            except Exception:
                pass
        if clip_with_audio is not None and clip_with_audio is not render_clip:
            try:
                clip_with_audio.close()
            except Exception:
                pass
        if composite_clip is not None:
            try:
                composite_clip.close()
            except Exception:
                pass
        try:
            timeline_clip.close()
        except Exception:
            pass
        for clip in clip_pool:
            try:
                clip.close()
            except Exception:
                continue


def restore_project_version(base_name: str, version: int) -> ProjectMetadata:
    metadata = load_project_version(base_name, version, OUTPUT_DIR)
    _touch(metadata)
    return save_project(metadata, OUTPUT_DIR)


def list_versions(base_name: str) -> List[ProjectVersionInfo]:
    return repository_list_versions(base_name, OUTPUT_DIR)


__all__ = [
    "add_subtitle",
    "update_subtitle",
    "delete_subtitle_line",
    "replace_timeline",
    "update_audio_settings",
    "delete_project",
    "render_project",
    "restore_project_version",
    "list_versions",
]
