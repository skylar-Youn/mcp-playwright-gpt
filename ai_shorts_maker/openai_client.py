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

    def translate_text(
        self,
        text_to_translate: str,
        target_lang: str,
        translation_mode: str,
        tone_hint: Optional[str] = None,
        prompt_hint: Optional[str] = None,
    ) -> str:
        """Translate text using the chat completion model."""
        logger.debug("Requesting translation to %s from model %s", target_lang, self.script_model)

        mode_map = {
            "literal": "Translate literally.",
            "adaptive": "Translate adaptively for a modern, natural-sounding video script.",
            "reinterpret": "Reinterpret the meaning freely to create a new, engaging script.",
        }
        mode_instruction = mode_map.get(translation_mode, mode_map["adaptive"])

        prompt = f"""Translate the following text into {target_lang}.

{mode_instruction}

Original text:
---
{text_to_translate}
---

Translated text:"""

        if tone_hint:
            prompt += f"\n\nMaintain a {tone_hint} tone."
        if prompt_hint:
            prompt += f"\n\nConsider this hint: {prompt_hint}"

        response = self.client.chat.completions.create(
            model=self.script_model,
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert translator for short video scripts.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
        )
        translated_text = response.choices[0].message.content.strip()
        logger.debug("Received translation with %d characters", len(translated_text))
        return translated_text

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
