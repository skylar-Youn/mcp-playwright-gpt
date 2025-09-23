"""FastAPI 애플리케이션: AI 쇼츠 제작 웹 UI 및 API."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import APIRouter, Body, FastAPI, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from pydantic import BaseModel

from ai_shorts_maker.generator import GenerationOptions, generate_short
from ai_shorts_maker.models import (
    ProjectMetadata,
    ProjectSummary,
    ProjectVersionInfo,
    SubtitleCreate,
    SubtitleUpdate,
    TimelineUpdate,
)
from ai_shorts_maker.repository import (
    delete_project as repository_delete_project,
    list_projects,
    load_project,
    metadata_path,
)
from ai_shorts_maker.services import (
    add_subtitle,
    delete_subtitle_line,
    list_versions,
    render_project,
    replace_timeline,
    restore_project_version,
    update_audio_settings,
    update_subtitle,
)


class RenderRequest(BaseModel):
    burn_subs: Optional[bool] = False

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
PACKAGE_DIR = BASE_DIR.parent / "ai_shorts_maker"
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

api_router = APIRouter(prefix="/api", tags=["projects"])


@api_router.get("/projects", response_model=List[ProjectSummary])
def api_list_projects() -> List[ProjectSummary]:
    return list_projects(OUTPUT_DIR)


@api_router.get("/projects/{base_name}", response_model=ProjectMetadata)
def api_get_project(base_name: str) -> ProjectMetadata:
    try:
        return load_project(base_name, OUTPUT_DIR)
    except FileNotFoundError as exc:  # pragma: no cover - handled as HTTP 404
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@api_router.post("/projects/{base_name}/subtitles", response_model=ProjectMetadata)
def api_add_subtitle(base_name: str, payload: SubtitleCreate) -> ProjectMetadata:
    try:
        return add_subtitle(base_name, payload)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@api_router.patch("/projects/{base_name}/subtitles/{subtitle_id}", response_model=ProjectMetadata)
def api_update_subtitle(base_name: str, subtitle_id: str, payload: SubtitleUpdate) -> ProjectMetadata:
    try:
        return update_subtitle(base_name, subtitle_id, payload)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@api_router.delete("/projects/{base_name}/subtitles/{subtitle_id}", response_model=ProjectMetadata)
def api_delete_subtitle(base_name: str, subtitle_id: str) -> ProjectMetadata:
    try:
        return delete_subtitle_line(base_name, subtitle_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@api_router.patch("/projects/{base_name}/timeline", response_model=ProjectMetadata)
def api_update_timeline(base_name: str, payload: TimelineUpdate) -> ProjectMetadata:
    try:
        return replace_timeline(base_name, payload)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@api_router.patch("/projects/{base_name}/audio", response_model=ProjectMetadata)
def api_update_audio(
    base_name: str,
    music_enabled: Optional[bool] = Body(None),
    music_volume: Optional[float] = Body(None),
    ducking: Optional[float] = Body(None),
    music_track: Optional[str] = Body(None),
) -> ProjectMetadata:
    try:
        return update_audio_settings(
            base_name,
            music_enabled=music_enabled,
            music_volume=music_volume,
            ducking=ducking,
            music_track=music_track,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@api_router.delete("/projects/{base_name}", status_code=status.HTTP_204_NO_CONTENT)
def api_delete_project(base_name: str) -> JSONResponse:
    try:
        repository_delete_project(base_name, OUTPUT_DIR)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return JSONResponse(status_code=status.HTTP_204_NO_CONTENT, content=None)


@api_router.post("/projects/{base_name}/render", response_model=ProjectMetadata)
def api_render_project(base_name: str, payload: Optional[RenderRequest] = Body(None)) -> ProjectMetadata:
    try:
        burn = payload.burn_subs if payload is not None else False
        return render_project(base_name, burn_subs=bool(burn))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@api_router.get("/projects/{base_name}/versions", response_model=List[ProjectVersionInfo])
def api_list_versions(base_name: str) -> List[ProjectVersionInfo]:
    return list_versions(base_name)


@api_router.post("/projects/{base_name}/versions/{version}/restore", response_model=ProjectMetadata)
def api_restore_version(base_name: str, version: int) -> ProjectMetadata:
    try:
        return restore_project_version(base_name, version)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


app.include_router(api_router)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    selected_base = request.query_params.get("existing")
    project_summaries = list_projects(OUTPUT_DIR)
    version_history: List[ProjectVersionInfo] = []
    version_history_json: List[Dict[str, Any]] = []
    result = None
    error = None

    if selected_base:
        try:
            project = load_project(selected_base, OUTPUT_DIR)
            result = build_result_payload(project)
            version_history = list_versions(selected_base)
            version_history_json = [item.model_dump(exclude_none=True) for item in version_history]
        except FileNotFoundError:
            error = f"'{selected_base}' 프로젝트를 찾을 수 없습니다."

    context = {
        "request": request,
        "form_values": default_form_values(),
        "result": result,
        "error": error,
        "project_summaries": project_summaries,
        "selected_project": selected_base,
        "version_history_json": version_history_json,
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

    version_history: List[ProjectVersionInfo] = []
    version_history_json: List[Dict[str, Any]] = []
    error = None

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

        generation_result = await run_in_threadpool(generate_short, options)
        base_name = generation_result.get("base_name")
        if base_name:
            project = load_project(base_name, OUTPUT_DIR)
            result = build_result_payload(project)
            version_history = list_versions(base_name)
            version_history_json = [item.model_dump(exclude_none=True) for item in version_history]
        else:
            result = build_result_payload_dict(generation_result)
            error = None
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("Generation error: %s", exc)
        result = None
        error = str(exc)

    selected_project = None
    if result and isinstance(result.get("metadata"), dict):
        selected_project = result["metadata"].get("base_name")

    context = {
        "request": request,
        "form_values": form_values,
        "result": result,
        "error": error,
        "project_summaries": list_projects(OUTPUT_DIR),
        "selected_project": selected_project,
        "version_history_json": version_history_json,
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


def build_result_payload(project: ProjectMetadata) -> Dict[str, Any]:
    metadata = project.model_dump(exclude_none=False)

    def relative_output(path_str: Optional[str]) -> Optional[str]:
        if not path_str:
            return None
        path = Path(path_str)
        try:
            return f"/outputs/{path.name}"
        except ValueError:
            return None

    metadata_json = json.dumps(metadata, ensure_ascii=False, indent=2, default=str)

    return {
        "metadata": metadata,
        "metadata_json": metadata_json,
        "video_url": relative_output(project.video_path),
        "audio_url": relative_output(project.audio_path),
        "srt_url": relative_output(project.subtitles_path),
        "json_url": relative_output(str(metadata_path(project.base_name, OUTPUT_DIR))),
    }


def build_result_payload_dict(metadata: Dict[str, Any]) -> Dict[str, Any]:
    def relative_output(path_str: Optional[str]) -> Optional[str]:
        if not path_str:
            return None
        path = Path(path_str)
        try:
            return f"/outputs/{path.name}"
        except ValueError:
            return None

    metadata_json = json.dumps(metadata, ensure_ascii=False, indent=2, default=str)
    return {
        "metadata": metadata,
        "metadata_json": metadata_json,
        "video_url": relative_output(metadata.get("video_path")),
        "audio_url": relative_output(metadata.get("audio_path")),
        "srt_url": relative_output(metadata.get("subtitles_path")),
        "json_url": relative_output(metadata.get("metadata_path")),
    }
