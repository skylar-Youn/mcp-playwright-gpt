"""FastAPI 애플리케이션: AI 쇼츠 제작 웹 UI."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from ai_shorts_maker.generator import GenerationOptions, generate_short

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
PACKAGE_DIR = Path(__file__).resolve().parent.parent / "ai_shorts_maker"
ASSETS_DIR = PACKAGE_DIR / "assets"
OUTPUT_DIR = PACKAGE_DIR / "outputs"
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

load_dotenv()
ASSETS_DIR.mkdir(parents=True, exist_ok=True)
(ASSETS_DIR / "broll").mkdir(exist_ok=True)
(ASSETS_DIR / "music").mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

app = FastAPI(title="AI Shorts Maker")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/outputs", StaticFiles(directory=OUTPUT_DIR), name="outputs")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    existing_param = request.query_params.get("existing")
    existing_outputs = list_existing_outputs()
    result = None
    error = None

    if existing_param:
        selected = build_existing_metadata(existing_param)
        if selected:
            result = build_result_payload(selected)
        else:
            error = f"'{existing_param}' 이름의 결과를 찾을 수 없습니다."

    context = {
        "request": request,
        "form_values": default_form_values(),
        "result": result,
        "error": error,
        "existing_outputs": existing_outputs,
    }
    return templates.TemplateResponse("index.html", context)


@app.post("/generate", response_class=HTMLResponse)
async def generate(
    request: Request,
    topic: str = Form(...),
    style: str = Form("정보/요약"),
    duration: int = Form(30),
    lang: str = Form("ko"),
    voice: str = Form("alloy"),
    fps: int = Form(24),
    music: Optional[str] = Form(None),
    music_volume: float = Form(0.12),
    ducking: float = Form(0.35),
    burn_subs: Optional[str] = Form(None),
    dry_run: Optional[str] = Form(None),
    save_json: Optional[str] = Form(None),
    output_name: Optional[str] = Form(None),
    script_model: str = Form("gpt-4o-mini"),
    tts_model: str = Form("gpt-4o-mini-tts"),
):
    form_values = {
        "topic": topic,
        "style": style,
        "duration": duration,
        "lang": lang,
        "voice": voice,
        "fps": fps,
        "music": music,
        "music_volume": music_volume,
        "ducking": ducking,
        "burn_subs": burn_subs,
        "dry_run": dry_run,
        "save_json": save_json,
        "output_name": output_name,
        "script_model": script_model,
        "tts_model": tts_model,
    }

    existing_outputs = list_existing_outputs()

    try:
        options = GenerationOptions(
            topic=topic,
            style=style,
            duration=duration,
            lang=lang,
            fps=fps,
            voice=voice,
            music=music is not None,
            music_volume=music_volume,
            ducking=ducking,
            burn_subs=burn_subs is not None,
            dry_run=dry_run is not None,
            save_json=save_json is not None,
            script_model=script_model,
            tts_model=tts_model,
            output_name=output_name or None,
        )

        metadata = await run_in_threadpool(generate_short, options)
        result = build_result_payload(metadata)
        error = None
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("Generation error: %s", exc)
        result = None
        error = str(exc)

    context = {
        "request": request,
        "form_values": form_values,
        "result": result,
        "error": error,
        "existing_outputs": existing_outputs,
    }
    return templates.TemplateResponse("index.html", context)


def default_form_values() -> Dict[str, Any]:
    return {
        "topic": "무서운 썰",
        "style": "공포/미스터리",
        "duration": 30,
        "lang": "ko",
        "voice": "alloy",
        "fps": 24,
        "music": "on",
        "music_volume": 0.12,
        "ducking": 0.35,
        "burn_subs": None,
        "dry_run": None,
        "save_json": None,
        "output_name": "",
        "script_model": "gpt-4o-mini",
        "tts_model": "gpt-4o-mini-tts",
    }


def build_result_payload(metadata: Dict[str, Any]) -> Dict[str, Any]:
    video_name = metadata.get("video_path")
    audio_name = metadata.get("audio_path")
    srt_name = metadata.get("subtitles_path")
    json_name = metadata.get("metadata_path")

    def relative_output(path_str: Optional[str]) -> Optional[str]:
        if not path_str:
            return None
        path = Path(path_str)
        try:
            return f"/outputs/{path.name}"
        except ValueError:
            return None

    return {
        "metadata": metadata,
        "video_url": relative_output(video_name),
        "audio_url": relative_output(audio_name),
        "srt_url": relative_output(srt_name),
        "json_url": relative_output(json_name),
    }


def list_existing_outputs() -> list[Dict[str, str]]:
    basenames = set()
    for path in OUTPUT_DIR.glob("*.*"):
        if path.name.startswith(".") or "_temp_" in path.name:
            continue
        basenames.add(path.stem)

    records: list[Dict[str, str]] = []
    for base in sorted(basenames):
        record = {"name": base, "label": base}
        video = OUTPUT_DIR / f"{base}.mp4"
        audio = OUTPUT_DIR / f"{base}.mp3"
        if video.exists():
            record["video_url"] = f"/outputs/{video.name}"
        if audio.exists():
            record["audio_url"] = f"/outputs/{audio.name}"
        records.append(record)
    return records


def build_existing_metadata(base_name: str) -> Dict[str, Any] | None:
    video_path = OUTPUT_DIR / f"{base_name}.mp4"
    audio_path = OUTPUT_DIR / f"{base_name}.mp3"
    srt_path = OUTPUT_DIR / f"{base_name}.srt"
    json_path = OUTPUT_DIR / f"{base_name}.json"
    script_path = OUTPUT_DIR / f"{base_name}.txt"

    if not any(
        path.exists()
        for path in [video_path, audio_path, srt_path, json_path, script_path]
    ):
        return None

    metadata: Dict[str, Any] = {
        "existing": True,
        "base_name": base_name,
        "video_path": str(video_path) if video_path.exists() else None,
        "audio_path": str(audio_path) if audio_path.exists() else None,
        "subtitles_path": str(srt_path) if srt_path.exists() else None,
        "metadata_path": str(json_path) if json_path.exists() else None,
        "script_path": str(script_path) if script_path.exists() else None,
    }
    return metadata
