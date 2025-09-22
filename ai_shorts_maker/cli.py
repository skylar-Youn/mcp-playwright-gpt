"""Command line interface for the AI Shorts Maker."""
from __future__ import annotations

import argparse
import logging
import sys

from dotenv import load_dotenv

from .generator import GenerationOptions, generate_short

logger = logging.getLogger(__name__)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AI-powered Shorts video generator")
    parser.add_argument("--topic", required=True, help="Short-form video topic")
    parser.add_argument("--style", default="정보/요약", help="Tone or niche style for the script")
    parser.add_argument("--duration", type=int, default=30, help="Target duration in seconds")
    parser.add_argument("--lang", default="ko", help="Language code (ko/en etc)")
    parser.add_argument("--fps", type=int, default=24, help="Video frames per second")
    parser.add_argument("--voice", default="alloy", help="OpenAI TTS voice name")
    parser.add_argument(
        "--music",
        action="store_true",
        dest="music",
        help="Enable background music if available",
    )
    parser.add_argument(
        "--no-music",
        action="store_false",
        dest="music",
        help="Disable background music",
    )
    parser.set_defaults(music=True)
    parser.add_argument("--music-volume", type=float, default=0.12, help="Background music base volume (0-1)")
    parser.add_argument("--ducking", type=float, default=0.35, help="Portion to reduce music loudness under narration")
    parser.add_argument("--save-json", action="store_true", help="Save generation metadata as JSON")
    parser.add_argument("--burn-subs", action="store_true", help="Render subtitles directly into the video")
    parser.add_argument("--dry-run", action="store_true", help="Generate script + subtitles only")
    parser.add_argument("--script-model", default="gpt-4o-mini", help="OpenAI model for script generation")
    parser.add_argument("--tts-model", default="gpt-4o-mini-tts", help="OpenAI TTS model")
    parser.add_argument("--output", help="Custom output filename (without extension)")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return parser.parse_args(argv)


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="[%(asctime)s] %(levelname)s - %(name)s: %(message)s",
    )


def run_generation(args: argparse.Namespace) -> dict:
    load_dotenv()

    configure_logging(args.log_level)

    options = GenerationOptions(
        topic=args.topic,
        style=args.style,
        duration=args.duration,
        lang=args.lang,
        fps=args.fps,
        voice=args.voice,
        music=args.music,
        music_volume=args.music_volume,
        ducking=args.ducking,
        burn_subs=args.burn_subs,
        dry_run=args.dry_run,
        save_json=args.save_json,
        script_model=args.script_model,
        tts_model=args.tts_model,
        output_name=args.output,
    )

    return generate_short(options)


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    args = parse_args(argv)
    try:
        run_generation(args)
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("Generation failed: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
