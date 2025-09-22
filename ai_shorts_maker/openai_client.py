"""OpenAI helper utilities."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from openai import OpenAI

logger = logging.getLogger(__name__)


class OpenAIShortsClient:
    """Wraps the OpenAI client for script and TTS generation."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        script_model: str = "gpt-4o-mini",
        tts_model: str = "gpt-4o-mini-tts",
    ) -> None:
        key = api_key or os.getenv("OPENAI_API_KEY")
        if not key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Export it or add it to a .env file."
            )

        self.client = OpenAI(api_key=key)
        self.script_model = script_model
        self.tts_model = tts_model

    def generate_script(self, prompt: str, temperature: float = 0.8) -> str:
        """Generate a script using the configured chat completion model."""
        logger.debug("Requesting script from OpenAI model %s", self.script_model)
        response = self.client.chat.completions.create(
            model=self.script_model,
            messages=[
                {
                    "role": "system",
                    "content": "You write concise, high-conversion short video scripts.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=temperature,
        )
        script = response.choices[0].message.content.strip()
        logger.debug("Received script with %d characters", len(script))
        return script

    def synthesize_voice(
        self,
        text: str,
        voice: str,
        output_path: Path,
        audio_format: str = "mp3",
    ) -> Path:
        """Generate an audio narration using the TTS model."""
        logger.debug(
            "Requesting TTS via model %s (voice=%s, format=%s)",
            self.tts_model,
            voice,
            audio_format,
        )
        response = self.client.audio.speech.create(
            model=self.tts_model,
            voice=voice,
            input=text,
            response_format=audio_format,
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "wb") as fh:
            for chunk in response.iter_bytes():
                fh.write(chunk)

        logger.debug("Saved narration to %s", output_path)
        return output_path
