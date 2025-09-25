"""Media helpers for assembling the short video."""
from __future__ import annotations

import inspect
import logging
import math
import os
import random
from collections import defaultdict, deque
from pathlib import Path
from typing import Iterable, List, Optional

import numpy as np

try:
    from moviepy.audio.fx import all as afx
except ImportError:  # moviepy>=2.0 renamed audio effects
    afx = None
    from moviepy.audio.fx.AudioFadeIn import AudioFadeIn
    from moviepy.audio.fx.AudioFadeOut import AudioFadeOut
    from moviepy.audio.fx.AudioLoop import AudioLoop
else:
    AudioFadeIn = AudioFadeOut = AudioLoop = None

try:
    from moviepy.editor import (
        AudioFileClip,
        ColorClip,
        CompositeAudioClip,
        CompositeVideoClip,
        ImageClip,
        TextClip,
        VideoClip,
        VideoFileClip,
        concatenate_videoclips,
    )
except ModuleNotFoundError:  # moviepy>=2.0 removes the editor shim
    from moviepy import (
        AudioFileClip,
        ColorClip,
        CompositeAudioClip,
        CompositeVideoClip,
        ImageClip,
        TextClip,
        VideoClip,
        VideoFileClip,
        concatenate_videoclips,
    )

try:
    from moviepy.video.fx import all as vfx
except ImportError:
    vfx = None
    from moviepy.video.fx.Loop import Loop
    from moviepy.video.fx.Resize import Resize as ResizeEffect
else:
    ResizeEffect = None

try:
    from moviepy.audio.fx.MultiplyVolume import MultiplyVolume
except ImportError:
    MultiplyVolume = None
from moviepy.video.tools.subtitles import SubtitlesClip

from .subtitles import CaptionLine

logger = logging.getLogger(__name__)

_TEXTCLIP_SIGNATURE = inspect.signature(TextClip.__init__)
_TEXT_PARAM = "text" if "text" in _TEXTCLIP_SIGNATURE.parameters else "txt"
_FONT_SIZE_PARAM = "font_size" if "font_size" in _TEXTCLIP_SIGNATURE.parameters else "fontsize"

SUPPORTED_BROLL_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".jpg", ".jpeg", ".png"}
SUPPORTED_MUSIC_EXTENSIONS = {".mp3", ".wav", ".m4a", ".flac"}

DEFAULT_FONT_CANDIDATES = [
    os.getenv("SHORTS_SUBTITLE_FONT"),
    "/usr/share/fonts/truetype/nanum/NanumSquareRoundR.ttf",
    "/usr/share/fonts/truetype/nanum/NanumSquareR.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]

FONT_SEARCH_DIRS = [
    Path(path).expanduser()
    for path in filter(
        None,
        [
            os.getenv("SHORTS_FONT_DIR"),
            "/usr/share/fonts/truetype/nanum",
            "/usr/share/fonts/opentype/noto",
            "/usr/share/fonts/truetype",
            "/usr/local/share/fonts",
            str(Path.home() / ".fonts"),
            str(Path.home() / ".local/share/fonts"),
        ],
    )
]

FONT_FILE_CANDIDATES = [
    "NanumSquareRoundR.ttf",
    "NanumSquareR.ttf",
    "NanumGothic.ttf",
    "NanumBarunGothic.ttf",
    "NanumBarunGothicLight.ttf",
    "NotoSansCJK-Regular.ttc",
    "NotoSansKR-Regular.otf",
    "NotoSansKR-Regular.ttc",
]


def _detect_font() -> Optional[str]:
    for candidate in DEFAULT_FONT_CANDIDATES:
        if not candidate:
            continue
        path = Path(candidate).expanduser()
        if path.exists():
            logger.debug("Using subtitle font candidate %s", path)
            return str(path)

    for directory in FONT_SEARCH_DIRS:
        if not directory or not directory.exists():
            continue
        for filename in FONT_FILE_CANDIDATES:
            candidate = directory / filename
            if candidate.exists():
                logger.debug("Detected subtitle font %s", candidate)
                return str(candidate)
        for pattern in ("Nanum*.ttf", "Nanum*.otf", "NotoSansCJK-*.ttc", "NotoSansKR*.otf", "NotoSansKR*.ttc"):
            try:
                match = next(directory.rglob(pattern))
            except (StopIteration, PermissionError, OSError):
                continue
            logger.debug("Detected subtitle font via pattern %s -> %s", pattern, match)
            return str(match)
    logger.warning("No subtitle font found; MoviePy default will be used")
    return None


def _resolve_font_path(font_path: Optional[str]) -> Optional[str]:
    if font_path:
        candidate = Path(font_path).expanduser()
        if candidate.exists():
            return str(candidate)
        logger.warning("Subtitle font '%s' not found; falling back to auto-detection", font_path)
    return _detect_font()


def _with_position(clip, position):
    if position is None:
        return clip
    if hasattr(clip, "with_position"):
        return clip.with_position(position)
    if hasattr(clip, "set_position"):
        return clip.set_position(position)
    clip.pos = position
    return clip


def _audio_loop(clip, duration: float):
    if hasattr(clip, "with_effects") and AudioLoop is not None:
        return clip.with_effects([AudioLoop(duration=duration)])
    if afx is not None and hasattr(afx, "audio_loop") and hasattr(clip, "fx"):
        return clip.fx(afx.audio_loop, duration=duration)
    return clip


def _audio_fadein(clip, duration: float):
    if hasattr(clip, "with_effects") and AudioFadeIn is not None:
        return clip.with_effects([AudioFadeIn(duration=duration)])
    if afx is not None and hasattr(afx, "audio_fadein") and hasattr(clip, "fx"):
        return clip.fx(afx.audio_fadein, duration)
    return clip


def _audio_fadeout(clip, duration: float):
    if hasattr(clip, "with_effects") and AudioFadeOut is not None:
        return clip.with_effects([AudioFadeOut(duration=duration)])
    if afx is not None and hasattr(afx, "audio_fadeout") and hasattr(clip, "fx"):
        return clip.fx(afx.audio_fadeout, duration)
    return clip


def _video_loop(clip, duration: float):
    if hasattr(clip, "with_effects") and Loop is not None:
        return clip.with_effects([Loop(duration=duration)])
    if vfx is not None and hasattr(vfx, "loop") and hasattr(clip, "fx"):
        return clip.fx(vfx.loop, duration=duration)
    return clip


def _clip_dimensions(clip) -> tuple[Optional[float], Optional[float]]:
    width = getattr(clip, "w", None)
    height = getattr(clip, "h", None)
    if width is not None and height is not None:
        return float(width), float(height)
    size = getattr(clip, "size", None)
    if isinstance(size, (list, tuple)) and len(size) == 2:
        width, height = size
        if width and height:
            return float(width), float(height)
    return None, None


def _resize_to_size(clip, size: tuple[int, int]):
    if hasattr(clip, "with_effects") and ResizeEffect is not None:
        try:
            return clip.with_effects([ResizeEffect(new_size=size)])
        except Exception:
            pass
    if hasattr(clip, "resized"):
        try:
            return clip.resized(new_size=size)
        except Exception:
            pass
    if hasattr(clip, "resize"):
        try:
            return clip.resize(size)
        except Exception:
            pass
    return clip


def _crop_to_size(clip, size: tuple[int, int]):
    target_w, target_h = size
    clip_w, clip_h = _clip_dimensions(clip)
    if clip_w is None or clip_h is None:
        return clip
    if abs(clip_w - target_w) < 1 and abs(clip_h - target_h) < 1:
        return clip
    x_center = clip_w / 2
    y_center = clip_h / 2
    if hasattr(clip, "crop"):
        try:
            return clip.crop(width=target_w, height=target_h, x_center=x_center, y_center=y_center)
        except Exception:
            pass
    if vfx is not None and hasattr(clip, "fx") and hasattr(vfx, "crop"):
        try:
            return clip.fx(vfx.crop, width=target_w, height=target_h, x_center=x_center, y_center=y_center)
        except Exception:
            pass
    return _resize_to_size(clip, size)


def _resize_clip(clip, size: tuple[int, int]):
    target_w, target_h = size
    clip_w, clip_h = _clip_dimensions(clip)
    if clip_w is None or clip_h is None or clip_w <= 0 or clip_h <= 0:
        return _resize_to_size(clip, size)

    scale = max(target_w / clip_w, target_h / clip_h)
    # ensure a small padding to avoid rounding gaps when cropping later
    scale = max(scale, 1.0)
    new_w = max(1, int(math.ceil(clip_w * scale)))
    new_h = max(1, int(math.ceil(clip_h * scale)))

    resized = _resize_to_size(clip, (new_w, new_h))
    return _crop_to_size(resized, size)


def _set_fps(clip, fps: int):
    if fps is None:
        return clip
    if hasattr(clip, "with_fps"):
        return clip.with_fps(fps)
    if hasattr(clip, "set_fps"):
        return clip.set_fps(fps)
    clip.fps = fps
    return clip


def _set_duration(clip, duration: float):
    if duration is None:
        return clip
    if hasattr(clip, "with_duration"):
        return clip.with_duration(duration)
    if hasattr(clip, "set_duration"):
        return clip.set_duration(duration)
    clip.duration = duration
    clip.end = getattr(clip, "start", 0) + duration
    return clip


def _subclip(clip, start: float, end: float):
    if hasattr(clip, "subclipped"):
        return clip.subclipped(start_time=start, end_time=end)
    if hasattr(clip, "subclip"):
        return clip.subclip(start, end)
    raise AttributeError("Clip does not support subclip/subclipped operations")


def _set_audio(video_clip, audio_clip):
    if hasattr(video_clip, "with_audio"):
        return video_clip.with_audio(audio_clip)
    if hasattr(video_clip, "set_audio"):
        return video_clip.set_audio(audio_clip)
    video_clip.audio = audio_clip
    return video_clip


def _adjust_volume(audio_clip, factor: float):
    if hasattr(audio_clip, "with_effects") and MultiplyVolume is not None:
        return audio_clip.with_effects([MultiplyVolume(factor=factor)])
    if hasattr(audio_clip, "volumex"):
        return audio_clip.volumex(factor)
    if afx is not None and hasattr(afx, "volumex") and hasattr(audio_clip, "fx"):
        return audio_clip.fx(afx.volumex, factor)
    return audio_clip


class MediaFactory:
    def __init__(
        self,
        assets_dir: Path,
        canvas_size: tuple[int, int] = (1080, 1920),
        fps: int = 24,
        subtitle_font: Optional[str] = None,
        subtitle_fontsize: int = 62,
        subtitle_y_offset: int = 0,
        subtitle_stroke_width: int = 2,
        subtitle_animation: str = "none",
        layout_template: str = "classic",
        banner_primary: Optional[str] = None,
        banner_secondary: Optional[str] = None,
        banner_primary_font_size: Optional[int] = None,
        banner_secondary_font_size: Optional[int] = None,
        banner_line_spacing: Optional[int] = None,
    ) -> None:
        self.assets_dir = assets_dir
        self.broll_dir = assets_dir / "broll"
        self.music_dir = assets_dir / "music"
        self.canvas_size = canvas_size
        self.fps = fps
        self.subtitle_font = _resolve_font_path(subtitle_font)
        self.subtitle_fontsize = subtitle_fontsize
        self.subtitle_y_offset = subtitle_y_offset
        self.subtitle_stroke_width = subtitle_stroke_width
        self.subtitle_animation = (subtitle_animation or "none").lower()
        self.layout_template = (layout_template or "classic").lower()
        self.banner_primary_text = banner_primary
        self.banner_secondary_text = banner_secondary
        self.banner_primary_font_size = banner_primary_font_size
        self.banner_secondary_font_size = banner_secondary_font_size
        self.banner_line_spacing = banner_line_spacing

    # -------------------- B-roll --------------------
    def build_broll_clip(self, duration: float):
        candidates = list(self.iter_broll_files())
        if not candidates:
            logger.info("No b-roll assets found; using a solid color background")
            return _set_fps(
                ColorClip(size=self.canvas_size, color=(15, 15, 20), duration=duration),
                self.fps,
            )

        random.shuffle(candidates)
        clips: List = []
        remaining = duration
        for path in candidates:
            clip = self._load_broll_clip(path)
            if clip is None:
                continue
            clip_duration = getattr(clip, "duration", None)
            if clip_duration is not None and clip_duration >= remaining:
                trimmed = _subclip(clip, 0, remaining)
                resized = _resize_clip(trimmed, self.canvas_size)
                clips.append(_set_fps(resized, self.fps))
                remaining = 0
                break
            resized = _resize_clip(clip, self.canvas_size)
            clips.append(_set_fps(resized, self.fps))
            if clip_duration is not None:
                remaining = max(0.0, remaining - clip_duration)

        if remaining > 0 and clips:
            filler = _video_loop(clips[-1], duration=remaining)
            clips.append(filler)
            remaining = 0

        if not clips:
            return _set_fps(
                ColorClip(size=self.canvas_size, color=(15, 15, 20), duration=duration),
                self.fps,
            )

        combined = (
            clips[0]
            if len(clips) == 1
            else concatenate_videoclips(clips, method="compose")
        )
        combined = _set_duration(combined, duration)
        return _set_fps(combined, self.fps)

    def iter_broll_files(self) -> Iterable[Path]:
        if not self.broll_dir.exists():
            return []
        return [p for p in self.broll_dir.iterdir() if p.suffix.lower() in SUPPORTED_BROLL_EXTENSIONS]

    def _load_broll_clip(self, path: Path):
        logger.debug("Loading b-roll asset %s", path)
        if path.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"}:
            return VideoFileClip(str(path))
        if path.suffix.lower() in {".jpg", ".jpeg", ".png"}:
            clip = ImageClip(str(path), duration=6)
            return _set_fps(clip, self.fps)
        return None

    # -------------------- Audio --------------------
    def attach_audio(
        self,
        video_clip,
        narration_audio: Path,
        music_volume: float = 0.12,
        ducking: float = 0.35,
        use_music: bool = True,
        music_path: Optional[Path] = None,
    ) -> tuple:
        voice = AudioFileClip(str(narration_audio))
        base_audio = voice
        selected_track: Optional[Path] = None
        if use_music:
            track = music_path if music_path is not None else self.pick_music_track()
            if track:
                selected_track = track
                music = AudioFileClip(str(track))
                music = _adjust_volume(music, max(music_volume, 0.0))
                time_candidates = [
                    value
                    for value in [voice.duration, getattr(video_clip, "duration", None)]
                    if value is not None
                ]
                fallback_duration = next(
                    (value for value in [voice.duration, getattr(video_clip, "duration", None)] if value is not None),
                    0,
                )
                loop_target = max(time_candidates, default=fallback_duration) + 1
                music = _audio_loop(music, duration=loop_target)
                music = _audio_fadein(music, 1.5)
                music = _audio_fadeout(music, 1.5)
                music = _adjust_volume(music, max(1.0 - ducking, 0.05))
                base_audio = CompositeAudioClip([music, voice])

        target_candidates = [
            value
            for value in [getattr(video_clip, "duration", None), getattr(voice, "duration", None)]
            if value is not None
        ]
        target_duration = max(target_candidates, default=None)
        if target_duration is not None:
            final_audio = _set_duration(base_audio, target_duration)
        else:
            final_audio = base_audio
        return _set_audio(video_clip, final_audio), selected_track

    def pick_music_track(self) -> Optional[Path]:
        tracks = [p for p in self.music_dir.glob("*") if p.suffix.lower() in SUPPORTED_MUSIC_EXTENSIONS]
        if not tracks:
            logger.info("No background music found; continuing without BGM")
            return None
        return random.choice(tracks)

    # -------------------- Subtitles --------------------
    def burn_subtitles(self, video_clip, captions: List[CaptionLine]):
        if not captions:
            return video_clip

        animation_mode = self.subtitle_animation
        durations = [max(cap.end - cap.start, 0.1) for cap in captions]
        timings = [(cap.start, cap.end) for cap in captions]
        caption_lookup: dict[str, deque[tuple[float, float, float]]] = defaultdict(deque)
        for cap in captions:
            caption_lookup[cap.text].append(
                (max(cap.end - cap.start, 0.1), cap.start, cap.end)
            )
        if durations:
            default_duration = durations[-1]
            default_start, default_end = timings[-1]
        else:
            default_duration = 1.5
            default_start, default_end = 0.0, 1.5
        base_y = self.canvas_size[1] - 250 - self.subtitle_y_offset
        banner_enabled = self.layout_template == "banner"
        banner_height = int(self.canvas_size[1] * 0.21) if banner_enabled else 0
        if banner_enabled:
            base_y = self.canvas_size[1] - 300 - self.subtitle_y_offset
        slide_modes = {"slide_up", "slide_down", "slide_left", "slide_right"}

        def _caption_meta(text: str) -> tuple[float, float, float]:
            queue = caption_lookup.get(text)
            if queue:
                try:
                    return queue.popleft()
                except IndexError:
                    pass
            return default_duration, default_start, default_end

        def _create_text_clip(txt: str):
            base_kwargs = dict(
                color="white",
                method="caption",
                size=(self.canvas_size[0] - 120, None),
                stroke_color="black",
                stroke_width=self.subtitle_stroke_width,
            )

            def _make_kwargs(include_font: bool):
                kwargs = dict(base_kwargs)
                kwargs[_TEXT_PARAM] = txt
                kwargs[_FONT_SIZE_PARAM] = self.subtitle_fontsize
                if include_font and self.subtitle_font:
                    kwargs["font"] = self.subtitle_font
                return kwargs

            try:
                clip = TextClip(**_make_kwargs(include_font=True))
            except Exception:
                clip = TextClip(**_make_kwargs(include_font=False))
            return clip

        def generator(txt):
            raw_duration, start_time, _ = _caption_meta(txt)
            duration = max(raw_duration, 0.1)
            clip = _set_duration(_create_text_clip(txt), duration + 0.05)
            if hasattr(clip, "with_mask"):
                clip = clip.with_mask()

            base_frame = None
            mask_frame = None
            if animation_mode in {"typewriter", "fire"}:
                base_frame = clip.get_frame(0)
                if getattr(clip, "mask", None) is not None:
                    mask_frame = clip.mask.get_frame(0)

            if animation_mode in slide_modes:
                offset_y = self.canvas_size[1] * 0.08
                offset_x = self.canvas_size[0] * 0.12

                def pos_func(t: float):
                    local_t = max(0.0, t - start_time)
                    progress = min(max(local_t / 0.25, 0.0), 1.0)
                    slide = 1.0 - progress
                    if animation_mode == "slide_up":
                        return ("center", base_y + offset_y * slide)
                    if animation_mode == "slide_down":
                        return ("center", base_y - offset_y * slide)
                    if animation_mode == "slide_left":
                        return (
                            self.canvas_size[0] / 2 + offset_x * slide,
                            base_y,
                        )
                    return (
                        self.canvas_size[0] / 2 - offset_x * slide,
                        base_y,
                    )

                clip = _with_position(clip, pos_func)
            elif animation_mode == "bounce":
                amplitude = self.subtitle_fontsize * 0.45

                def bounce_position(t: float):
                    if duration <= 0:
                        return ("center", base_y)
                    local_t = max(0.0, t - start_time)
                    progress = max(0.0, min(local_t / duration, 1.0))
                    bounce = math.sin(progress * math.pi * 2.2)
                    decay = math.exp(-2.2 * progress)
                    return ("center", base_y - amplitude * bounce * decay)

                clip = _with_position(clip, bounce_position)
            elif animation_mode == "typewriter":
                if base_frame is None:
                    base_frame = clip.get_frame(0)
                total_w = base_frame.shape[1]

                def make_typewriter_frame(t: float):
                    frame = base_frame.copy()
                    local_t = max(0.0, t - start_time)
                    progress = max(0.0, min(local_t / max(duration, 1e-3), 1.0))
                    cutoff = int(total_w * progress)
                    if cutoff < frame.shape[1]:
                        frame[:, cutoff:, ...] = 0
                    return frame

                animated = VideoClip(make_typewriter_frame, duration=duration + 0.05)
                if mask_frame is not None:
                    total_mask_w = mask_frame.shape[1]

                    def make_typewriter_mask(t: float):
                        mask = mask_frame.copy()
                        local_t = max(0.0, t - start_time)
                        progress = max(0.0, min(local_t / max(duration, 1e-3), 1.0))
                        cutoff = int(total_mask_w * progress)
                        if cutoff < mask.shape[1]:
                            mask[:, cutoff:] = 0
                        return mask

                    animated.mask = VideoClip(make_typewriter_mask, is_mask=True, duration=duration + 0.05)
                clip = animated
            elif animation_mode == "highlight":
                pad_x = int(self.subtitle_fontsize * 0.9)
                pad_y = int(self.subtitle_fontsize * 0.6)
                clip_w, clip_h = _clip_dimensions(clip)
                box_w = int(max((clip_w or 0) + pad_x, self.canvas_size[0] // 3))
                box_h = int(max((clip_h or 0) + pad_y, self.subtitle_fontsize * 1.6))
                box = ColorClip(size=(box_w, box_h), color=(24, 30, 52))
                box = _set_duration(box, duration + 0.05)
                if hasattr(box, "with_opacity"):
                    box = box.with_opacity(0.55)
                elif hasattr(box, "set_opacity"):
                    box = box.set_opacity(0.55)
                centered_text = _with_position(clip, "center")
                clip = CompositeVideoClip(
                    [
                        box,
                        centered_text,
                    ],
                    size=(box_w, box_h),
                )
                clip = _set_duration(clip, duration + 0.05)
            elif animation_mode == "fire":
                if base_frame is None:
                    base_frame = clip.get_frame(0)
                def make_fire_frame(t: float):
                    local_t = max(0.0, t - start_time)
                    frame = base_frame.astype(np.float32).copy()
                    flicker = 0.6 + 0.4 * math.sin(local_t * 8.5)
                    warm = np.array([1.0, 0.55 + 0.35 * flicker, 0.25 + 0.2 * flicker], dtype=np.float32)
                    frame *= warm
                    return np.clip(frame, 0, 255).astype(np.uint8)

                animated = VideoClip(make_fire_frame, duration=duration + 0.05)
                if mask_frame is not None:
                    animated.mask = VideoClip(lambda t: mask_frame, is_mask=True, duration=duration + 0.05)
                clip = animated

            return clip

        subs = [((cap.start, cap.end), cap.text) for cap in captions]
        subtitles_clip = SubtitlesClip(subs, make_textclip=generator)
        if animation_mode not in slide_modes and animation_mode != "bounce":
            subtitles_clip = _with_position(subtitles_clip, ("center", base_y))
        video_duration = getattr(video_clip, "duration", None)
        if video_duration is not None:
            subtitles_clip = _set_duration(subtitles_clip, video_duration)
        layers = [video_clip, subtitles_clip]

        if banner_enabled:
            duration_target = video_duration or subtitles_clip.duration
            banner_bg = ColorClip(size=(self.canvas_size[0], banner_height), color=(0, 0, 0))
            banner_bg = _set_duration(banner_bg, duration_target)
            if hasattr(banner_bg, "with_opacity"):
                banner_bg = banner_bg.with_opacity(0.92)
            banner_bg = _with_position(banner_bg, ("center", 0))

            def _banner_text_clip(
                text: Optional[str],
                *,
                color: str,
                y_factor: float,
                font_size_override: Optional[int] = None,
                y_adjust: int = 0,
            ) -> Optional[VideoClip]:
                if not text:
                    return None
                base_kwargs = dict(
                    color=color,
                    method="caption",
                    size=(self.canvas_size[0] - 160, None),
                    stroke_color="black",
                    stroke_width=max(2, self.subtitle_stroke_width + 1),
                )

                def _make_kwargs(include_font: bool):
                    kwargs = dict(base_kwargs)
                    kwargs[_TEXT_PARAM] = text
                    size_value = font_size_override or max(int(self.subtitle_fontsize * 1.05), 48)
                    kwargs[_FONT_SIZE_PARAM] = max(size_value, 1)
                    if include_font and self.subtitle_font:
                        kwargs["font"] = self.subtitle_font
                    return kwargs

                try:
                    clip = TextClip(**_make_kwargs(include_font=True))
                except Exception:
                    clip = TextClip(**_make_kwargs(include_font=False))
                clip = _set_duration(clip, duration_target)
                y_pos = max(8, int(banner_height * y_factor) - clip.h // 2 + int(y_adjust))
                return _with_position(clip, ("center", y_pos))

            spacing_adjust = int(self.banner_line_spacing or 0)
            primary_adjust = -math.floor(spacing_adjust / 2)
            secondary_adjust = math.ceil(spacing_adjust / 2)

            primary_text = _banner_text_clip(
                self.banner_primary_text,
                color="white",
                y_factor=0.35,
                font_size_override=self.banner_primary_font_size,
                y_adjust=primary_adjust,
            )
            secondary_text = _banner_text_clip(
                self.banner_secondary_text,
                color="#ffd400",
                y_factor=0.72,
                font_size_override=self.banner_secondary_font_size,
                y_adjust=secondary_adjust,
            )

            layers.append(banner_bg)
            if primary_text is not None:
                layers.append(primary_text)
            if secondary_text is not None:
                layers.append(secondary_text)

        composite = CompositeVideoClip(layers, size=self.canvas_size)
        return _set_duration(composite, video_duration or subtitles_clip.duration)
