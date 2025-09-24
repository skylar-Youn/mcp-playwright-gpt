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

        lang_names = {
            "ko": "Korean",
            "ja": "Japanese",
            "en": "English"
        }
        target_lang_name = lang_names.get(target_lang, target_lang)

        prompt = f"""Translate the following text into {target_lang_name}.

{mode_instruction}

CRITICAL REQUIREMENTS:
- Return ONLY the translated text in {target_lang_name}
- NO English explanations, notes, or commentary
- NO phrases like "Here's", "Certainly", "This maintains"
- NO dashes (---) or formatting markers
- JUST the pure {target_lang_name} translation

Original text: {text_to_translate}"""

        if tone_hint:
            prompt += f"\n\nMaintain a {tone_hint} tone."
        if prompt_hint:
            prompt += f"\n\nConsider this hint: {prompt_hint}"

        response = self.client.chat.completions.create(
            model=self.script_model,
            messages=[
                {
                    "role": "system",
                    "content": f"You are a translator. Reply ONLY with the {target_lang_name} text. NO explanations. NO English. NO commentary. NO formatting.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,  # Lower temperature for more consistent output
        )
        translated_text = response.choices[0].message.content.strip()

        # Clean up common patterns that appear in responses
        translated_text = self._clean_translation_response(translated_text, target_lang)

        logger.debug("Received translation with %d characters", len(translated_text))
        return translated_text

    def _clean_translation_response(self, text: str, target_lang: str) -> str:
        """Clean up translation response to remove unwanted English explanations."""
        lines = text.split('\n')
        cleaned_lines = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Skip lines that are obviously English explanations
            english_starters = [
                'Sure!', 'Here\'s', 'Let me know', '---', 'Translation:', 'Translated text:',
                'Certainly!', 'I\'ll', 'This', 'The text', 'Here is', 'This maintains',
                'while conveying', 'meaning', 'tone'
            ]
            if any(line.startswith(starter) for starter in english_starters):
                continue

            # Skip lines containing common English explanation words
            english_words = [
                'reinterpretation', 'translation', 'maintains', 'convey', 'meaning',
                'tone', 'concise', 'same meaning', 'while', 'conveying'
            ]
            if any(word in line.lower() for word in english_words):
                continue

            if line.startswith('*') or line.endswith('*'):
                continue
            if line == '---' or line.startswith('---'):
                continue

            # For Japanese, skip lines that are mostly ASCII (likely English)
            if target_lang == 'ja':
                ascii_chars = sum(1 for c in line if ord(c) < 128)
                total_chars = len(line)
                if total_chars > 0 and ascii_chars / total_chars > 0.6:
                    continue

            # For Korean, skip lines that are mostly ASCII (likely English)
            if target_lang == 'ko':
                ascii_chars = sum(1 for c in line if ord(c) < 128)
                total_chars = len(line)
                if total_chars > 0 and ascii_chars / total_chars > 0.7:
                    continue

            cleaned_lines.append(line)

        result = '\n'.join(cleaned_lines).strip()

        # If we ended up with empty result, try to extract any non-ASCII text
        if not result and target_lang in ['ja', 'ko']:
            non_ascii_chars = []
            for char in text:
                if ord(char) > 127 or char in '。、？！':  # Include Japanese/Korean punctuation
                    non_ascii_chars.append(char)
            if non_ascii_chars:
                result = ''.join(non_ascii_chars).strip()

        return result

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
