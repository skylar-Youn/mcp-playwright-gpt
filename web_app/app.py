"""FastAPI 애플리케이션: AI 쇼츠 제작 웹 UI 및 API."""
from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Literal
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import (
    APIRouter,
    Body,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
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
    update_subtitle_style,
    update_subtitle,
)
from ai_shorts_maker.translator import (
    TranslatorProject,
    TranslatorProjectCreate,
    TranslatorProjectUpdate,
    aggregate_dashboard_projects,
    create_project as translator_create_project,
    delete_project as translator_delete_project,
    downloads_listing,
    ensure_directories as ensure_translator_directories,
    list_projects as translator_list_projects,
    load_project as translator_load_project,
    update_project as translator_update_project,
    UPLOADS_DIR,
)
from youtube.ytdl import download_with_options, parse_sub_langs


class RenderRequest(BaseModel):
    burn_subs: Optional[bool] = False


class SubtitleStyleRequest(BaseModel):
    font_size: Optional[int] = None
    y_offset: Optional[int] = None
    stroke_width: Optional[int] = None
    font_path: Optional[str] = None
    animation: Optional[str] = None
    template: Optional[str] = None
    banner_primary_text: Optional[str] = None
    banner_secondary_text: Optional[str] = None


class DashboardProject(BaseModel):
    id: str
    title: str
    project_type: Literal["shorts", "translator"]
    status: Literal["draft", "segmenting", "translating", "voice_ready", "rendering", "rendered", "failed"]
    completed_steps: int = 1
    total_steps: int = 5
    topic: Optional[str] = None
    language: Optional[str] = None
    thumbnail: Optional[str] = None
    updated_at: Optional[str] = None
    source_origin: Optional[str] = None


logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
PACKAGE_DIR = BASE_DIR.parent / "ai_shorts_maker"
ASSETS_DIR = PACKAGE_DIR / "assets"
OUTPUT_DIR = PACKAGE_DIR / "outputs"
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
YTDL_SETTINGS_PATH = BASE_DIR / "ytdl_settings.json"
DEFAULT_YTDL_OUTPUT_DIR = (BASE_DIR.parent / "youtube" / "download").resolve()
DEFAULT_YTDL_SETTINGS: Dict[str, Any] = {
    "output_dir": str(DEFAULT_YTDL_OUTPUT_DIR),
    "sub_langs": "ko",
    "sub_format": "srt/best",
    "download_subs": True,
    "auto_subs": True,
    "dry_run": False,
}

LANG_OPTIONS: List[tuple[str, str]] = [
    ("ko", "한국어"),
    ("en", "English"),
    ("ja", "日本語"),
]
LANG_OPTION_SET = {code for code, _ in LANG_OPTIONS}


def sanitize_lang(value: Optional[str]) -> str:
    if not value:
        return "ko"
    value_lower = value.lower()
    return value_lower if value_lower in LANG_OPTION_SET else "ko"


def _path_exists(value: Optional[str]) -> bool:
    if not value:
        return False
    try:
        return Path(value).exists()
    except OSError:
        return False


def build_dashboard_project(summary: ProjectSummary) -> DashboardProject:
    audio_ready = _path_exists(summary.audio_path)
    video_ready = _path_exists(summary.video_path)

    completed_steps = 1
    status: Literal["draft", "translating", "voice_ready", "rendering", "rendered", "failed"] = "draft"

    if audio_ready:
        completed_steps = max(completed_steps, 3)
        status = "voice_ready"
    if video_ready:
        completed_steps = 4
        status = "rendered"

    updated_at = summary.updated_at.isoformat() if summary.updated_at else None

    return DashboardProject(
        id=summary.base_name,
        title=summary.topic or summary.base_name,
        topic=summary.topic,
        language=summary.language,
        status=status,
        completed_steps=completed_steps,
        thumbnail=summary.video_path,
        updated_at=updated_at,
    )


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
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@api_router.patch("/projects/{base_name}/subtitles/{subtitle_id}", response_model=ProjectMetadata)
def api_update_subtitle(base_name: str, subtitle_id: str, payload: SubtitleUpdate) -> ProjectMetadata:
    try:
        return update_subtitle(base_name, subtitle_id, payload)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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


@api_router.patch("/projects/{base_name}/subtitle-style", response_model=ProjectMetadata)
def api_update_subtitle_style_route(base_name: str, payload: SubtitleStyleRequest) -> ProjectMetadata:
    try:
        data = payload.model_dump(exclude_unset=True)
        return update_subtitle_style(base_name, **data)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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


def default_ytdl_form() -> Dict[str, Any]:
    settings = load_ytdl_settings()
    return {
        "urls": "",
        **settings,
    }


def load_ytdl_settings() -> Dict[str, Any]:
    settings = DEFAULT_YTDL_SETTINGS.copy()
    if YTDL_SETTINGS_PATH.exists():
        try:
            data = json.loads(YTDL_SETTINGS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for key, value in data.items():
                    if key in settings:
                        if isinstance(settings[key], bool):
                            settings[key] = bool(value)
                        else:
                            settings[key] = value
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to load YTDL settings: %s", exc)
    return settings


def save_ytdl_settings(values: Dict[str, Any]) -> None:
    payload = {}
    for key in DEFAULT_YTDL_SETTINGS:
        if key not in values:
            continue
        original = DEFAULT_YTDL_SETTINGS[key]
        value = values[key]
        if isinstance(original, bool):
            payload[key] = bool(value)
        else:
            payload[key] = value
    try:
        YTDL_SETTINGS_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("Failed to save YTDL settings: %s", exc)


def _split_urls(raw: str) -> List[str]:
    return [line.strip() for line in raw.replace("\r", "\n").splitlines() if line.strip()]


@app.get("/ytdl", response_class=HTMLResponse)
async def ytdl_index(request: Request) -> HTMLResponse:
    context = {
        "request": request,
        "form_values": default_ytdl_form(),
        "result": None,
        "error": None,
        "settings_saved": False,
    }
    return templates.TemplateResponse("ytdl.html", context)


@app.post("/ytdl", response_class=HTMLResponse)
async def ytdl_download(
    request: Request,
    urls: str = Form(""),
    output_dir: str = Form(""),
    sub_langs: str = Form("ko"),
    sub_format: str = Form("srt/best"),
    download_subs: Optional[str] = Form("on"),
    auto_subs: Optional[str] = Form("on"),
    dry_run: Optional[str] = Form(None),
    save_settings: Optional[str] = Form(None),
) -> HTMLResponse:
    download_subs_enabled = download_subs is not None
    auto_subs_enabled = auto_subs is not None
    dry_run_enabled = dry_run is not None

    form_values = {
        "urls": urls,
        "output_dir": output_dir,
        "sub_langs": sub_langs,
        "sub_format": sub_format,
        "download_subs": download_subs_enabled,
        "auto_subs": auto_subs_enabled,
        "dry_run": dry_run_enabled,
    }

    settings_saved = False
    if save_settings is not None:
        settings_payload = {key: value for key, value in form_values.items() if key != "urls"}
        try:
            save_ytdl_settings(settings_payload)
            settings_saved = True
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Failed to save YTDL settings: %s", exc)

    parsed_urls = _split_urls(urls)
    error = None
    result: Optional[Dict[str, Any]] = None

    if parsed_urls:
        try:
            selected_langs = parse_sub_langs(sub_langs)
            files = await run_in_threadpool(
                download_with_options,
                parsed_urls,
                output_dir or None,
                skip_download=dry_run_enabled,
                download_subs=download_subs_enabled,
                auto_subs=auto_subs_enabled,
                sub_langs=sub_langs,
                sub_format=sub_format,
            )
            result = {
                "files": [str(path) for path in files],
                "count": len(files),
                "langs": selected_langs,
                "dry_run": dry_run_enabled,
            }
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("YT download error: %s", exc)
            error = str(exc)
    elif not settings_saved:
        error = "최소 하나의 유효한 URL을 입력하세요."

    context = {
        "request": request,
        "form_values": form_values,
        "error": error,
        "result": result,
        "settings_saved": settings_saved,
    }
    return templates.TemplateResponse("ytdl.html", context)


@app.get("/api/dashboard/projects", response_model=List[DashboardProject])
async def api_dashboard_projects(query: Optional[str] = None) -> List[DashboardProject]:
    summaries = list_projects(OUTPUT_DIR)
    projects = [build_dashboard_project(item) for item in summaries]

    if query:
        q = query.strip().lower()
        if q:
            projects = [
                project
                for project in projects
                if q in project.id.lower()
                or q in project.title.lower()
                or (project.topic and q in project.topic.lower())
                or (project.language and q in project.language.lower())
            ]

    return projects


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    summaries = list_projects(OUTPUT_DIR)
    projects = [build_dashboard_project(item).model_dump() for item in summaries]

    context = {
        "request": request,
        "projects": projects,
    }
    return templates.TemplateResponse("dashboard.html", context)


@app.get("/shorts", response_class=HTMLResponse)
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
        "lang_options": LANG_OPTIONS,
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
    lang = sanitize_lang(lang)

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
        "lang_options": LANG_OPTIONS,
    }
    return templates.TemplateResponse("index.html", context)


def default_form_values() -> Dict[str, Any]:
    return {
        "topic": "무서운 썰",
        "style": "공포/미스터리",
        "duration": 30,
        "lang": sanitize_lang("ko"),
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
