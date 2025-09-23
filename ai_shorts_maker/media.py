"""Media helpers for assembling the short video."""
from __future__ import annotations

import logging
import random
from pathlib import Path
from typing import Iterable, List, Optional

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

SUPPORTED_BROLL_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".jpg", ".jpeg", ".png"}
SUPPORTED_MUSIC_EXTENSIONS = {".mp3", ".wav", ".m4a", ".flac"}


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


def _resize_clip(clip, size: tuple[int, int]):
    if hasattr(clip, "resized"):
        return clip.resized(new_size=size)
    if hasattr(clip, "resize"):
        return clip.resize(size)
    if hasattr(clip, "with_effects") and ResizeEffect is not None:
        return clip.with_effects([ResizeEffect(new_size=size)])
    return clip


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
    ) -> None:
        self.assets_dir = assets_dir
        self.broll_dir = assets_dir / "broll"
        self.music_dir = assets_dir / "music"
        self.canvas_size = canvas_size
        self.fps = fps

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

        def generator(txt):
            return TextClip(
                txt,
                fontsize=62,
                font="Arial",
                color="white",
                method="caption",
                size=(self.canvas_size[0] - 120, None),
                stroke_color="black",
                stroke_width=2,
            )

        subs = [((cap.start, cap.end), cap.text) for cap in captions]
        subtitles_clip = SubtitlesClip(subs, generator)
        subtitles_clip = subtitles_clip.set_position(("center", self.canvas_size[1] - 250))
        video_duration = getattr(video_clip, "duration", None)
        if video_duration is not None:
            subtitles_clip = _set_duration(subtitles_clip, video_duration)
        composite = CompositeVideoClip([video_clip, subtitles_clip])
        return _set_duration(composite, video_duration or subtitles_clip.duration)
