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

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None  # type: ignore

try:
    from moviepy.video.fx.Resize import Resize as ResizeEffect
except ImportError:  # pragma: no cover - legacy moviepy
    ResizeEffect = None

try:
    from moviepy.video.fx import all as vfx
except ImportError:  # pragma: no cover - legacy moviepy
    vfx = None

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


def _with_opacity(clip, opacity: float):
    if opacity is None:
        return clip
    if hasattr(clip, "with_opacity"):
        return clip.with_opacity(opacity)
    if hasattr(clip, "set_opacity"):
        return clip.set_opacity(opacity)
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
UNSET = object()


def _touch(metadata: ProjectMetadata) -> None:
    metadata.version += 1
    metadata.updated_at = datetime.utcnow()


def _round_time(value: Optional[float], *, digits: int = 1) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(round(float(value), digits))
    except (TypeError, ValueError):
        return None


def add_subtitle(base_name: str, payload: SubtitleCreate) -> ProjectMetadata:
    metadata = load_project(base_name)
    start = _round_time(payload.start)
    end = _round_time(payload.end)
    if start is None or end is None:
        raise ValueError("Invalid subtitle timing")
    new_line = SubtitleLine(
        id=str(uuid4()),
        start=start,
        end=end,
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
        rounded = _round_time(payload.start)
        if rounded is None:
            raise ValueError("Invalid start time")
        target.start = rounded
    if payload.end is not None:
        rounded = _round_time(payload.end)
        if rounded is None:
            raise ValueError("Invalid end time")
        target.end = rounded
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


def update_subtitle_style(
    base_name: str,
    *,
    font_size: Optional[int] = None,
    y_offset: Optional[int] = None,
    stroke_width: Optional[int] = None,
    font_path: Optional[str] | object = UNSET,
    animation: Optional[str] = None,
    template: Optional[str] = None,
    banner_primary_text: Optional[str] = None,
    banner_secondary_text: Optional[str] = None,
    banner_primary_font_size: Optional[int] | object = UNSET,
    banner_secondary_font_size: Optional[int] | object = UNSET,
    banner_line_spacing: Optional[int] | object = UNSET,
) -> ProjectMetadata:
    metadata = load_project(base_name)
    style = metadata.subtitle_style
    if font_size is not None:
        style.font_size = font_size
    if y_offset is not None:
        style.y_offset = y_offset
    if stroke_width is not None:
        style.stroke_width = stroke_width
    if font_path is not UNSET:
        style.font_path = (font_path or None)
    if animation is not None:
        style.animation = animation
    if template is not None:
        style.template = template
    if banner_primary_text is not None:
        style.banner_primary_text = banner_primary_text
    if banner_secondary_text is not None:
        style.banner_secondary_text = banner_secondary_text
    if banner_primary_font_size is not UNSET:
        style.banner_primary_font_size = banner_primary_font_size
    if banner_secondary_font_size is not UNSET:
        style.banner_secondary_font_size = banner_secondary_font_size
    if banner_line_spacing is not UNSET:
        style.banner_line_spacing = banner_line_spacing
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


def _auto_motion_parameters(
    canvas_size: tuple[int, int],
    mode: str,
    base_scale: float,
    strength: float,
    shift_ratio: Optional[float],
) -> dict[str, Optional[float | tuple[float, float]]]:
    width, height = canvas_size

    mode = (mode or "kenburns").lower()
    strength = max(0.0, min(strength, 0.5))
    shift_ratio = shift_ratio if shift_ratio is not None else strength * 0.65
    shift_ratio = max(0.0, min(shift_ratio, 0.3))
    base_scale = max(base_scale, 1.0)
    base_scale = max(base_scale, 1.0 + shift_ratio * 1.25)

    desired_shift_x = width * shift_ratio * 0.5
    desired_shift_y = height * shift_ratio * 0.5

    def shift_limit(scale: float, axis: str) -> float:
        if axis == "x":
            return max(width * (scale - 1.0) / 2.0, 0.0)
        return max(height * (scale - 1.0) / 2.0, 0.0)

    def clamp_shift(scale_a: float, scale_b: float, desired: float, axis: str) -> float:
        limit = min(shift_limit(scale_a, axis), shift_limit(scale_b, axis))
        if limit <= 0:
            return 0.0
        return max(min(desired, limit * 0.95), -limit * 0.95)

    if mode in {"none", "off"}:
        return {
            "scale_start": None,
            "scale_end": None,
            "center_start": (0.0, 0.0),
            "center_end": (0.0, 0.0),
        }

    if mode == "zoom_out":
        scale_start = base_scale * (1.0 + strength)
        scale_end = base_scale
        return {
            "scale_start": scale_start,
            "scale_end": scale_end,
            "center_start": (0.0, 0.0),
            "center_end": (0.0, 0.0),
        }

    if mode == "zoom_in":
        scale_start = base_scale
        scale_end = base_scale * (1.0 + strength)
        return {
            "scale_start": scale_start,
            "scale_end": scale_end,
            "center_start": (0.0, 0.0),
            "center_end": (0.0, 0.0),
        }

    if mode == "pan_left":
        scale_start = base_scale
        scale_end = max(base_scale, base_scale * (1.0 + strength * 0.1))
        shift = clamp_shift(scale_start, scale_end, desired_shift_x, "x")
        return {
            "scale_start": scale_start,
            "scale_end": scale_end,
            "center_start": (shift, 0.0),
            "center_end": (-shift, 0.0),
        }

    if mode == "pan_right":
        scale_start = base_scale
        scale_end = max(base_scale, base_scale * (1.0 + strength * 0.1))
        shift = clamp_shift(scale_start, scale_end, desired_shift_x, "x")
        return {
            "scale_start": scale_start,
            "scale_end": scale_end,
            "center_start": (-shift, 0.0),
            "center_end": (shift, 0.0),
        }

    if mode == "pan_up":
        scale_start = base_scale
        scale_end = max(base_scale, base_scale * (1.0 + strength * 0.1))
        shift = clamp_shift(scale_start, scale_end, desired_shift_y, "y")
        return {
            "scale_start": scale_start,
            "scale_end": scale_end,
            "center_start": (0.0, shift),
            "center_end": (0.0, -shift),
        }

    if mode == "pan_down":
        scale_start = base_scale
        scale_end = max(base_scale, base_scale * (1.0 + strength * 0.1))
        shift = clamp_shift(scale_start, scale_end, desired_shift_y, "y")
        return {
            "scale_start": scale_start,
            "scale_end": scale_end,
            "center_start": (0.0, -shift),
            "center_end": (0.0, shift),
        }

    # Default: ken burns style (zoom in with gentle vertical drift)
    scale_start = base_scale
    scale_end = base_scale * (1.0 + strength)
    shift = clamp_shift(scale_start, scale_end, desired_shift_y, "y")
    return {
        "scale_start": scale_start,
        "scale_end": scale_end,
        "center_start": (0.0, shift),
        "center_end": (0.0, -shift),
    }


def _load_image_clip(path: Path) -> ImageClip:
    """Load an image clip from disk with a Pillow fallback."""

    try:
        return ImageClip(str(path))
    except (OSError, ValueError, RuntimeError) as original_exc:
        if Image is None:
            raise
        try:
            with Image.open(path) as img:
                # Ensure consistent color mode
                if img.mode != "RGB":
                    img = img.convert("RGB")
                else:
                    img = img.copy()
        except Exception as pillow_exc:  # pragma: no cover - fallback failure
            raise original_exc from pillow_exc

        import numpy as np  # Local import to avoid mandatory dependency if unused

        frame = np.array(img)
        return ImageClip(frame)


def _segment_to_clip(
    segment: TimelineSegment,
    factory: MediaFactory,
    fps: int,
    fallback_color: tuple[int, int, int] = (15, 15, 20),
) -> VideoFileClip:
    duration = max(segment.end - segment.start, 0.1)
    path = _resolve_media_path(segment.source)
    is_auto_source = segment.source in {None, "", "auto"}

    clip = None
    if path:
        try:
            if path.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"}:
                clip = VideoFileClip(str(path))
            elif path.suffix.lower() in {".jpg", ".jpeg", ".png"}:
                clip = _load_image_clip(path)
        except (OSError, ValueError, RuntimeError):
            clip = None

    if clip is None:
        if not is_auto_source:
            raise RuntimeError(f"Media source not found or unreadable: {segment.source}")
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

    extras = segment.extras if isinstance(segment.extras, dict) else {}

    position = extras.get("position")
    position_end = extras.get("position_end")
    if isinstance(position, list):
        position = tuple(position)
    if isinstance(position_end, list):
        position_end = tuple(position_end)
    is_image_segment = segment.media_type in {"image", "image_overlay"}
    auto_motion_enabled = extras.get("auto_motion", True)
    auto_mode = str(extras.get("auto_motion_mode", "kenburns") or "kenburns")
    auto_strength = extras.get("auto_motion_strength", 0.12)
    auto_base_scale = extras.get("auto_motion_base_scale", 1.1)
    auto_shift = extras.get("auto_motion_shift", None)

    def _as_float(value, default=None):
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    scale_start = extras.get("scale_start")
    scale_end = extras.get("scale_end")
    center_start = None
    center_end = None

    manual_scale = scale_start is not None or scale_end is not None
    manual_position = position is not None or position_end is not None

    if (
        is_image_segment
        and auto_motion_enabled
        and auto_mode.lower() not in {"none", "off"}
        and not manual_scale
        and not manual_position
    ):
        params = _auto_motion_parameters(
            factory.canvas_size,
            auto_mode,
            _as_float(auto_base_scale, 1.1) or 1.1,
            _as_float(auto_strength, 0.12) or 0.12,
            _as_float(auto_shift, None),
        )
        center_start = params.get("center_start", center_start)
        center_end = params.get("center_end", center_end)
        scale_start = params.get("scale_start", scale_start)
        scale_end = params.get("scale_end", scale_end)

    def _apply_scale_effect(target_clip, scale):
        def _sanitize(value):
            if callable(value):
                def wrapper(t: float):
                    result = value(t)
                    try:
                        return max(float(result), 1.0)
                    except (TypeError, ValueError):
                        return result

                return wrapper
            try:
                return max(float(value), 1.0)
            except (TypeError, ValueError):
                return value

        scale_clamped = _sanitize(scale)
        if hasattr(target_clip, "with_effects") and ResizeEffect is not None:
            try:
                return target_clip.with_effects([ResizeEffect(new_size=scale_clamped)])
            except Exception:
                pass
        if hasattr(target_clip, "resize"):
            try:
                return target_clip.resize(scale_clamped)
            except Exception:
                pass
        if hasattr(target_clip, "resized"):
            try:
                return target_clip.resized(new_size=scale_clamped)
            except Exception:
                pass
        if vfx is not None and hasattr(target_clip, "fx") and hasattr(vfx, "resize"):
            try:
                return target_clip.fx(vfx.resize, scale_clamped)
            except Exception:
                pass
        return target_clip

    if scale_start is None:
        scale_start = extras.get("scale_start")
    if scale_end is None:
        scale_end = extras.get("scale_end")

    scale_start_val = _as_float(scale_start, None)
    scale_end_val = _as_float(scale_end, None)
    if scale_start_val is None and scale_end_val is None:
        scale_start_val = 1.0
        scale_end_val = 1.0
    else:
        if scale_start_val is None:
            scale_start_val = 1.0
        if scale_end_val is None:
            scale_end_val = scale_start_val

    apply_scale_effect = (
        scale_start is not None
        or scale_end is not None
        or scale_start_val != 1.0
        or scale_end_val != 1.0
    )

    if apply_scale_effect:
        try:
            if abs(scale_end_val - scale_start_val) < 1e-3:
                clip = _apply_scale_effect(clip, scale_start_val)
            else:
                def scale_func(t: float):
                    if duration <= 0:
                        return scale_end_val
                    ratio = max(0.0, min(t / duration, 1.0))
                    return scale_start_val + (scale_end_val - scale_start_val) * ratio

                clip = _apply_scale_effect(clip, scale_func)
        except Exception:
            pass

    def _center_to_top_left(scale_value: float, center_offset: tuple[float, float]):
        scale_value = max(scale_value, 1.0)
        margin_x = factory.canvas_size[0] * (scale_value - 1.0) / 2.0
        margin_y = factory.canvas_size[1] * (scale_value - 1.0) / 2.0
        cx = max(min(center_offset[0], margin_x), -margin_x)
        cy = max(min(center_offset[1], margin_y), -margin_y)
        return (-margin_x + cx, -margin_y + cy)

    pos_start = None
    pos_end = None
    use_auto = False

    if position is not None:
        pos_start = position
        pos_end = position_end if position_end is not None else pos_start
    elif center_start is not None or center_end is not None:
        start_center = center_start or (0.0, 0.0)
        end_center = center_end or start_center
        pos_start = _center_to_top_left(scale_start_val, start_center)
        pos_end = _center_to_top_left(scale_end_val, end_center)
        use_auto = True
    else:
        pos_start = "center" if _is_overlay(segment) else (0.0, 0.0)
        pos_end = pos_start

    if isinstance(pos_start, tuple) and isinstance(pos_end, tuple) and any(abs(a - b) > 1e-3 for a, b in zip(pos_start, pos_end)):
        if use_auto:
            start_center = center_start or (0.0, 0.0)
            end_center = center_end or start_center

            def pos_func(t: float):
                if duration <= 0:
                    ratio = 1.0
                else:
                    ratio = max(0.0, min(t / duration, 1.0))
                scale_value = scale_start_val + (scale_end_val - scale_start_val) * ratio
                current_center = (
                    start_center[0] + (end_center[0] - start_center[0]) * ratio,
                    start_center[1] + (end_center[1] - start_center[1]) * ratio,
                )
                return _center_to_top_left(scale_value, current_center)

            clip = _with_position(clip, pos_func)
        else:
            def pos_func(t: float):
                if duration <= 0:
                    return pos_end
                ratio = max(0.0, min(t / duration, 1.0))
                x = pos_start[0] + (pos_end[0] - pos_start[0]) * ratio
                y = pos_start[1] + (pos_end[1] - pos_start[1]) * ratio
                return (x, y)

            clip = _with_position(clip, pos_func)
    else:
        if isinstance(pos_start, tuple):
            clip = _with_position(clip, tuple(pos_start))
        else:
            clip = _with_position(clip, pos_start)

    if pos_start is None and _is_overlay(segment):
        clip = _with_position(clip, "center")

    alpha = extras.get("alpha")
    if alpha is not None:
        try:
            clip = _with_opacity(clip, float(alpha))
        except (ValueError, TypeError):
            pass

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

    style = metadata.subtitle_style
    factory = MediaFactory(
        ASSETS_DIR,
        fps=fps,
        subtitle_font=style.font_path,
        subtitle_fontsize=style.font_size,
        subtitle_y_offset=style.y_offset,
        subtitle_stroke_width=style.stroke_width,
        subtitle_animation=style.animation,
        layout_template=style.template,
        banner_primary=style.banner_primary_text if style.banner_primary_text is not None else metadata.topic,
        banner_secondary=style.banner_secondary_text if style.banner_secondary_text is not None else metadata.style,
        banner_primary_font_size=style.banner_primary_font_size,
        banner_secondary_font_size=style.banner_secondary_font_size,
        banner_line_spacing=style.banner_line_spacing,
    )
    if style.font_path != factory.subtitle_font:
        style.font_path = factory.subtitle_font
    if style.template != factory.layout_template:
        style.template = factory.layout_template

    base_segments = [seg for seg in timeline_segments if not _is_overlay(seg)]
    overlay_segments = [seg for seg in timeline_segments if _is_overlay(seg)]

    clips: List[VideoFileClip] = []
    clip_pool: List[VideoFileClip] = []
    overlay_clips: List[VideoFileClip] = []
    try:
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

        for segment in overlay_segments:
            seg_duration = max(segment.end - segment.start, 0.0)
            if seg_duration <= 0:
                continue
            clip = _segment_to_clip(segment, factory, fps)
            clip = _with_start(clip, segment.start)
            clip = _with_end(clip, segment.end)
            overlay_clips.append(clip)
            clip_pool.append(clip)
    except Exception:
        for clip in clip_pool:
            try:
                clip.close()
            except Exception:
                pass
        raise

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
    "update_subtitle_style",
    "delete_project",
    "render_project",
    "restore_project_version",
    "list_versions",
]
