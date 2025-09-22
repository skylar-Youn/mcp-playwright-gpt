"""Prompt templates for AI Shorts Maker."""
from __future__ import annotations

from textwrap import dedent


def build_script_prompt(topic: str, style: str, lang: str, duration: int) -> str:
    """Return the instruction used to generate a short-form video script."""
    language_hint = {
        "ko": "한국어",
        "en": "English",
    }.get(lang.lower(), lang)

    return dedent(
        f"""
        Create a {duration}-second short-form video script in {language_hint}.
        Topic: {topic}
        Tone or style: {style}

        Requirements:
        - Use an engaging hook in the first sentence.
        - Keep the total script length suitable for a voice-over of about {duration} seconds.
        - Split the script into concise sentences separated by newline characters.
        - Return only the script, without additional commentary.
        """
    ).strip()
