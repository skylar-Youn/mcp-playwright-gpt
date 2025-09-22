"""Core generation workflow for AI Shorts Maker."""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

try:
    from moviepy.editor import AudioFileClip
except ModuleNotFoundError:  # moviepy>=2.0 removes the editor module
    from moviepy import AudioFileClip

from .media import MediaFactory
from .openai_client import OpenAIShortsClient
from .prompts import build_script_prompt
from .subtitles import (
    allocate_caption_timings,
    split_script_into_sentences,
    write_srt_file,
)

logger = logging.getLogger(__name__)


@dataclass
class GenerationOptions:
    topic: str
    style: str = "정보/요약"
    duration: int = 30
    lang: str = "ko"
    fps: int = 24
    voice: str = "alloy"
    music: bool = True
    music_volume: float = 0.12
    ducking: float = 0.35
    burn_subs: bool = False
    dry_run: bool = False
    save_json: bool = False
    script_model: str = "gpt-4o-mini"
    tts_model: str = "gpt-4o-mini-tts"
    output_name: Optional[str] = None
    assets_dir: Path = field(
        default_factory=lambda: Path(__file__).resolve().parent / "assets"
    )
    output_dir: Path = field(
        default_factory=lambda: Path(__file__).resolve().parent / "outputs"
    )


def build_output_name(topic: str, style: str, lang: str, custom: str | None = None) -> str:
    if custom:
        return custom
    slug = "-".join(part for part in [topic, style, lang] if part)
    slug = slug.replace("/", "-")
    slug = "-".join(filter(None, slug.split()))
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    return f"{timestamp}-{slug}"


def ensure_directories(options: GenerationOptions) -> None:
    (options.assets_dir / "broll").mkdir(parents=True, exist_ok=True)
    (options.assets_dir / "music").mkdir(parents=True, exist_ok=True)
    options.output_dir.mkdir(parents=True, exist_ok=True)


def generate_short(options: GenerationOptions) -> Dict[str, Any]:
    ensure_directories(options)

    openai_client = OpenAIShortsClient(
        script_model=options.script_model,
        tts_model=options.tts_model,
    )

    prompt = build_script_prompt(options.topic, options.style, options.lang, options.duration)
    logger.info("Generating script...")
    script_text = openai_client.generate_script(prompt)
    sentences = split_script_into_sentences(script_text)

    output_name = build_output_name(
        options.topic,
        options.style,
        options.lang,
        options.output_name,
    )

    script_path = options.output_dir / f"{output_name}.txt"
    script_path.write_text(script_text, encoding="utf-8")
    logger.info("Saved script to %s", script_path)

    metadata: Dict[str, Any] = {
        "topic": options.topic,
        "style": options.style,
        "language": options.lang,
        "duration_target": options.duration,
        "sentences": sentences,
        "script": script_text,
        "script_path": str(script_path),
        "base_name": output_name,
    }

    if options.dry_run:
        if options.save_json:
            json_path = options.output_dir / f"{output_name}.json"
            json_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2))
            logger.info("Saved metadata to %s", json_path)
            metadata["metadata_path"] = str(json_path)
        return metadata

    # Voice synthesis
    narration_path = options.output_dir / f"{output_name}.mp3"
    logger.info("Generating narration audio (%s)...", options.voice)
    openai_client.synthesize_voice(
        text=script_text,
        voice=options.voice,
        output_path=narration_path,
    )

    narration_clip = AudioFileClip(str(narration_path))
    voice_duration = narration_clip.duration

    captions = allocate_caption_timings(sentences, voice_duration)
    srt_path = options.output_dir / f"{output_name}.srt"
    write_srt_file(captions, srt_path)
    logger.info("Saved subtitles to %s", srt_path)

    media_factory = MediaFactory(options.assets_dir, fps=options.fps)
    logger.info("Building background visuals (duration %.2fs)...", voice_duration)
    background_clip = media_factory.build_broll_clip(voice_duration)

    video_with_audio = media_factory.attach_audio(
        background_clip,
        narration_path,
        music_volume=options.music_volume,
        ducking=options.ducking,
        use_music=options.music,
    )

    if options.burn_subs:
        logger.info("Burning subtitles into the video")
        video_with_audio = media_factory.burn_subtitles(video_with_audio, captions)

    output_video_path = options.output_dir / f"{output_name}.mp4"
    logger.info("Rendering final video to %s", output_video_path)
    try:
        video_with_audio.write_videofile(
            str(output_video_path),
            fps=options.fps,
            codec="libx264",
            audio_codec="aac",
            temp_audiofile=str(options.output_dir / f"{output_name}_temp_audio.m4a"),
            remove_temp=True,
            threads=os.cpu_count() or 4,
        )
    finally:
        narration_clip.close()
        background_clip.close()
        video_with_audio.close()

    metadata.update(
        {
            "audio_path": str(narration_path),
            "video_path": str(output_video_path),
            "subtitles_path": str(srt_path),
            "captions": [cap.__dict__ for cap in captions],
        }
    )

    if options.save_json:
        json_path = options.output_dir / f"{output_name}.json"
        json_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2))
        logger.info("Saved metadata to %s", json_path)
        metadata["metadata_path"] = str(json_path)

    return metadata
