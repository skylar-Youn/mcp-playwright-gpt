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
    translate_project_segments,
    synthesize_voice_for_project,
    render_translated_project,
    list_translation_versions,
    load_translation_version,
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
    status: Literal["draft", "segmenting", "translating", "voice_ready", "voice_complete", "rendering", "rendered", "failed"]
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
YTDL_HISTORY_PATH = BASE_DIR / "ytdl_history.json"
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


translator_router = APIRouter(prefix="/api/translator", tags=["translator"])


@translator_router.get("/downloads")
async def api_list_downloads() -> List[Dict[str, str]]:
    return downloads_listing()


@translator_router.get("/settings")
def api_get_translator_settings() -> Dict[str, Any]:
    return load_translator_settings()


@translator_router.post("/settings")
def api_save_translator_settings(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    try:
        save_translator_settings(payload)
        return {"success": True, "message": "Settings saved successfully"}
    except Exception as exc:
        logger.exception("Failed to save translator settings")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@translator_router.post("/projects", response_model=TranslatorProject)
async def api_create_translator_project(payload: TranslatorProjectCreate) -> TranslatorProject:
    try:
        settings_to_save = {
            "target_lang": payload.target_lang,
            "translation_mode": payload.translation_mode,
            "tone_hint": payload.tone_hint,
        }
        save_translator_settings(settings_to_save)
        return await run_in_threadpool(translator_create_project, payload)
    except Exception as exc:
        logger.exception("Failed to create translator project")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@translator_router.get("/projects/{project_id}", response_model=TranslatorProject)
async def api_get_translator_project(project_id: str) -> TranslatorProject:
    try:
        return await run_in_threadpool(translator_load_project, project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@translator_router.patch("/projects/{project_id}", response_model=TranslatorProject)
async def api_update_translator_project(
    project_id: str, payload: TranslatorProjectUpdate
) -> TranslatorProject:
    try:
        return await run_in_threadpool(translator_update_project, project_id, payload)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@translator_router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def api_delete_translator_project(project_id: str) -> None:
    try:
        await run_in_threadpool(translator_delete_project, project_id)
    except FileNotFoundError:
        pass  # Idempotent delete
    except Exception as exc:
        logger.exception("Failed to delete translator project %s", project_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@translator_router.post("/projects/{project_id}/generate-commentary", response_model=TranslatorProject)
async def api_generate_ai_commentary(project_id: str) -> TranslatorProject:
    try:
        from ai_shorts_maker.translator import generate_ai_commentary_for_project
        return await run_in_threadpool(generate_ai_commentary_for_project, project_id)
    except Exception as exc:
        logger.exception("Failed to generate AI commentary for project %s", project_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@translator_router.post("/projects/{project_id}/translate", response_model=TranslatorProject)
async def api_translate_project(project_id: str) -> TranslatorProject:
    try:
        return await run_in_threadpool(translate_project_segments, project_id)
    except Exception as exc:
        logger.exception("Failed to run translation for project %s", project_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@translator_router.post("/projects/{project_id}/voice", response_model=TranslatorProject)
async def api_synthesize_voice(project_id: str) -> TranslatorProject:
    try:
        return await run_in_threadpool(synthesize_voice_for_project, project_id)
    except Exception as exc:
        logger.exception("Failed to run voice synthesis for project %s", project_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@translator_router.post("/projects/{project_id}/render", response_model=TranslatorProject)
async def api_render_project(project_id: str) -> TranslatorProject:
    try:
        return await run_in_threadpool(render_translated_project, project_id)
    except Exception as exc:
        logger.exception("Failed to run render for project %s", project_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@translator_router.get("/projects/{project_id}/versions")
async def api_list_translation_versions(project_id: str):
    try:
        return await run_in_threadpool(list_translation_versions, project_id)
    except Exception as exc:
        logger.exception("Failed to list translation versions for project %s", project_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@translator_router.get("/projects/{project_id}/versions/{version}")
async def api_get_translation_version(project_id: str, version: int):
    try:
        result = await run_in_threadpool(load_translation_version, project_id, version)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Version {version} not found")
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to load translation version %s for project %s", version, project_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@translator_router.post("/projects/{project_id}/reverse-translate")
async def api_reverse_translate(project_id: str, payload: Dict[str, Any] = Body(...)):
    try:
        segment_id = payload.get("segment_id")
        japanese_text = payload.get("japanese_text", "").strip()

        if not japanese_text:
            raise HTTPException(status_code=400, detail="Japanese text is required")

        # Use the existing translate_project_segments function with reverse parameters
        from ai_shorts_maker.translator import translate_text

        korean_text = await run_in_threadpool(
            translate_text,
            japanese_text,
            target_lang="ko",  # Japanese to Korean
            translation_mode="reinterpret",
            tone_hint=None
        )

        return {"korean_text": korean_text}

    except Exception as exc:
        logger.exception("Failed to reverse translate text for project %s", project_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@translator_router.patch("/projects/{project_id}/segments")
async def api_update_segment_text(project_id: str, payload: Dict[str, Any] = Body(...)):
    try:
        segment_id = payload.get("segment_id")
        text_type = payload.get("text_type")
        text_value = payload.get("text_value", "")

        if not segment_id or not text_type:
            raise HTTPException(status_code=400, detail="segment_id and text_type are required")

        from ai_shorts_maker.translator import update_segment_text

        await run_in_threadpool(update_segment_text, project_id, segment_id, text_type, text_value)

        return {"success": True}

    except Exception as exc:
        logger.exception("Failed to update segment text for project %s", project_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@translator_router.patch("/projects/{project_id}/segments/time")
async def api_update_segment_time(project_id: str, payload: Dict[str, Any] = Body(...)):
    try:
        segment_id = payload.get("segment_id")
        start_time = payload.get("start_time")
        end_time = payload.get("end_time")

        if not segment_id or start_time is None or end_time is None:
            raise HTTPException(status_code=400, detail="segment_id, start_time, and end_time are required")

        if start_time >= end_time:
            raise HTTPException(status_code=400, detail="start_time must be less than end_time")

        if start_time < 0 or end_time < 0:
            raise HTTPException(status_code=400, detail="times must be non-negative")

        from ai_shorts_maker.translator import update_segment_time

        await run_in_threadpool(update_segment_time, project_id, segment_id, float(start_time), float(end_time))

        return {"success": True}

    except Exception as exc:
        logger.exception("Failed to update segment time for project %s", project_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@translator_router.patch("/projects/{project_id}/voice-synthesis-mode")
async def api_update_voice_synthesis_mode(project_id: str, payload: Dict[str, Any] = Body(...)):
    try:
        voice_synthesis_mode = payload.get("voice_synthesis_mode")

        if not voice_synthesis_mode:
            raise HTTPException(status_code=400, detail="voice_synthesis_mode is required")

        if voice_synthesis_mode not in ["subtitle", "commentary", "both"]:
            raise HTTPException(status_code=400, detail="voice_synthesis_mode must be one of: subtitle, commentary, both")

        from ai_shorts_maker.translator import load_project, save_project

        project = await run_in_threadpool(load_project, project_id)
        project.voice_synthesis_mode = voice_synthesis_mode
        await run_in_threadpool(save_project, project)

        return {"success": True, "voice_synthesis_mode": voice_synthesis_mode}

    except Exception as exc:
        logger.exception("Failed to update voice synthesis mode for project %s", project_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


app.include_router(translator_router)


# Video Editor Router
video_editor_router = APIRouter(prefix="/api/video-editor", tags=["video-editor"])


class VideoProcessRequest(BaseModel):
    project_id: str
    video_path: str
    template: str
    subtitle_type: str = "translated"  # translated, original, reverse, external
    external_subtitle_path: Optional[str] = None  # 외부 자막 파일 경로


@video_editor_router.post("/process")
async def api_process_video(payload: VideoProcessRequest) -> Dict[str, Any]:
    try:
        # 프로젝트 로드
        project = await run_in_threadpool(translator_load_project, payload.project_id)

        # 영상 처리 실행
        result = await run_in_threadpool(
            process_video_with_subtitles,
            payload.project_id,
            payload.video_path,
            payload.template,
            payload.subtitle_type,
            project,
            payload.external_subtitle_path
        )

        return {"success": True, "result": result}
    except Exception as exc:
        logger.exception("Failed to process video for project %s", payload.project_id)
        return {"success": False, "error": str(exc)}


@video_editor_router.get("/subtitle-preview")
async def api_subtitle_preview(path: str) -> Dict[str, Any]:
    """외부 자막 파일의 미리보기를 제공"""
    try:
        subtitle_path = Path(path)

        if not subtitle_path.exists():
            return {"success": False, "error": "파일을 찾을 수 없습니다"}

        if not subtitle_path.suffix.lower() in ['.srt', '.vtt', '.ass']:
            return {"success": False, "error": "지원하지 않는 자막 파일 형식입니다"}

        # 파일 크기 체크 (10MB 제한)
        if subtitle_path.stat().st_size > 10 * 1024 * 1024:
            return {"success": False, "error": "파일이 너무 큽니다"}

        # 파일 내용 읽기 (처음 1000자만)
        with open(subtitle_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read(1000)

        # 줄 단위로 나누어 처음 10줄만 보여주기
        lines = content.split('\n')[:10]
        preview = '\n'.join(lines)

        if len(content) >= 1000:
            preview += "\n\n... (더 많은 내용이 있습니다)"

        return {"success": True, "preview": preview}

    except Exception as exc:
        logger.exception("Failed to load subtitle preview")
        return {"success": False, "error": str(exc)}


app.include_router(video_editor_router)


def process_video_with_subtitles(project_id: str, video_path: str, template: str, subtitle_type: str, project: Any, external_subtitle_path: Optional[str] = None) -> Dict[str, Any]:
    """영상에 번역된 자막을 합성하는 함수"""
    import subprocess
    from pathlib import Path
    import tempfile
    import os

    try:
        # 출력 디렉토리 설정
        output_dir = PACKAGE_DIR / "outputs" / "video_editor"
        output_dir.mkdir(parents=True, exist_ok=True)

        # SRT 파일 생성 (선택된 자막 타입 사용)
        if subtitle_type == "external" and external_subtitle_path:
            # 외부 자막 파일 사용
            srt_file_path = external_subtitle_path
        else:
            # 프로젝트 자막 사용
            srt_content = generate_srt_from_project(project, subtitle_type)

            # 임시 SRT 파일 생성
            with tempfile.NamedTemporaryFile(mode='w', suffix='.srt', delete=False, encoding='utf-8') as srt_file:
                srt_file.write(srt_content)
                srt_file_path = srt_file.name

        # 출력 파일명 생성
        video_name = Path(video_path).stem
        output_filename = f"{project_id}_{video_name}_{template}.mp4"
        output_path = output_dir / output_filename

        # FFmpeg 명령어 구성 (템플릿에 따른 자막 스타일)
        subtitle_style = get_subtitle_style_for_template(template)

        ffmpeg_cmd = [
            'ffmpeg', '-y',  # -y: 출력 파일 덮어쓰기
            '-i', video_path,  # 입력 영상
            '-vf', f"subtitles={srt_file_path}:force_style='{subtitle_style}'",  # 자막 필터
            '-c:a', 'copy',  # 오디오 복사
            str(output_path)  # 출력 경로
        ]

        # FFmpeg 실행
        logger.info(f"Running FFmpeg command: {' '.join(ffmpeg_cmd)}")
        result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, check=True)

        # 임시 파일 정리 (외부 파일이 아닌 경우만)
        if subtitle_type != "external":
            os.unlink(srt_file_path)

        return {
            "output_path": str(output_path),
            "output_filename": output_filename,
            "template_used": template,
            "video_duration": get_video_duration(video_path)
        }

    except subprocess.CalledProcessError as exc:
        logger.error(f"FFmpeg error: {exc.stderr}")
        raise RuntimeError(f"영상 처리 중 오류 발생: {exc.stderr}")
    except Exception as exc:
        logger.exception("Video processing failed")
        raise RuntimeError(f"영상 처리 실패: {str(exc)}")


def generate_srt_from_project(project: Any, subtitle_type: str = "translated") -> str:
    """프로젝트의 세그먼트에서 SRT 형식의 자막 생성"""
    srt_lines = []

    for i, segment in enumerate(project.segments, 1):
        # 세그먼트 속성 이름 확인 (start/end vs start_time/end_time)
        start_time = getattr(segment, 'start', getattr(segment, 'start_time', 0))
        end_time = getattr(segment, 'end', getattr(segment, 'end_time', 1))

        # 선택된 자막 타입에 따라 텍스트 선택
        if subtitle_type == "original":
            text = getattr(segment, 'source_text', None)
        elif subtitle_type == "reverse":
            text = getattr(segment, 'reverse_translated_text', None)
        else:  # translated (기본값)
            text = getattr(segment, 'translated_text', None)

        # 텍스트가 없으면 다른 텍스트로 대체
        if not text:
            text = getattr(segment, 'translated_text', None) or \
                   getattr(segment, 'source_text', None) or \
                   getattr(segment, 'original_text', '(자막 없음)')

        # 시간을 SRT 형식으로 변환 (HH:MM:SS,mmm)
        start_srt = format_time_for_srt(start_time)
        end_srt = format_time_for_srt(end_time)

        srt_lines.append(str(i))
        srt_lines.append(f"{start_srt} --> {end_srt}")
        srt_lines.append(text)
        srt_lines.append("")  # 빈 줄

    return "\n".join(srt_lines)


def format_time_for_srt(seconds: float) -> str:
    """초를 SRT 형식의 타임코드로 변환"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millisecs = int((seconds - int(seconds)) * 1000)

    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millisecs:03d}"


def get_subtitle_style_for_template(template: str) -> str:
    """템플릿에 따른 자막 스타일 반환"""
    styles = {
        "classic": "FontSize=24,PrimaryColour=&Hffffff,OutlineColour=&H000000,BackColour=&H80000000,Bold=1,Outline=2,Shadow=1,Alignment=2,MarginV=20",
        "banner": "FontSize=26,PrimaryColour=&Hffffff,OutlineColour=&H000000,BackColour=&H80ff0000,Bold=1,Outline=2,Shadow=1,Alignment=2,MarginV=300"
    }
    return styles.get(template, styles["classic"])


def get_video_duration(video_path: str) -> Optional[float]:
    """영상의 지속시간을 초 단위로 반환"""
    try:
        import subprocess
        cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', video_path]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        import json
        data = json.loads(result.stdout)
        return float(data['format']['duration'])
    except Exception as exc:
        logger.warning(f"Failed to get video duration: {exc}")
        return None


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


def load_download_history() -> List[Dict[str, Any]]:
    """Load download history from JSON file."""
    if not YTDL_HISTORY_PATH.exists():
        return []
    try:
        data = json.loads(YTDL_HISTORY_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to load download history: %s", exc)
        return []


def save_download_history(history: List[Dict[str, Any]]) -> None:
    """Save download history to JSON file."""
    try:
        YTDL_HISTORY_PATH.write_text(
            json.dumps(history, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("Failed to save download history: %s", exc)


def add_to_download_history(urls: List[str], files: List[Path], settings: Dict[str, Any]) -> None:
    """Add download record to history."""
    history = load_download_history()

    download_record = {
        "timestamp": datetime.now().isoformat(),
        "urls": urls,
        "files": [str(f) for f in files],
        "settings": {
            "output_dir": settings.get("output_dir"),
            "sub_langs": settings.get("sub_langs"),
            "download_subs": settings.get("download_subs"),
            "auto_subs": settings.get("auto_subs"),
        }
    }

    history.insert(0, download_record)  # Add to beginning
    # Keep only last 100 records
    history = history[:100]

    save_download_history(history)


def delete_download_files(file_paths: List[str]) -> Dict[str, Any]:
    """Delete downloaded files and return result."""
    deleted = []
    errors = []

    for file_path in file_paths:
        try:
            path = Path(file_path)
            if path.exists():
                path.unlink()
                deleted.append(file_path)

                # Also try to delete related files (subtitles, etc.)
                base_name = path.stem
                parent_dir = path.parent
                for related_file in parent_dir.glob(f"{base_name}.*"):
                    if related_file != path and related_file.exists():
                        related_file.unlink()
                        deleted.append(str(related_file))
            else:
                errors.append(f"File not found: {file_path}")
        except Exception as exc:
            errors.append(f"Error deleting {file_path}: {str(exc)}")

    return {"deleted": deleted, "errors": errors}


TRANSLATOR_SETTINGS_PATH = BASE_DIR / "translator_settings.json"
DEFAULT_TRANSLATOR_SETTINGS: Dict[str, Any] = {
    "target_lang": "ja",
    "translation_mode": "reinterpret",
    "tone_hint": "드라마하고 유쾌하먼서 유머러스하게",
}

def load_translator_settings() -> Dict[str, Any]:
    settings = DEFAULT_TRANSLATOR_SETTINGS.copy()
    if TRANSLATOR_SETTINGS_PATH.exists():
        try:
            data = json.loads(TRANSLATOR_SETTINGS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                settings.update(data)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to load Translator settings: %s", exc)
    return settings

def save_translator_settings(values: Dict[str, Any]) -> None:
    payload = {}
    for key in DEFAULT_TRANSLATOR_SETTINGS:
        if key in values and values[key] is not None:
            payload[key] = values[key]
    try:
        TRANSLATOR_SETTINGS_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("Failed to save Translator settings: %s", exc)


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


@app.get("/api/ytdl/history")
async def api_get_download_history() -> List[Dict[str, Any]]:
    """Get download history."""
    return load_download_history()


@app.delete("/api/ytdl/files")
async def api_delete_files(file_paths: List[str] = Body(...)) -> Dict[str, Any]:
    """Delete downloaded files."""
    return delete_download_files(file_paths)


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

            # Add to download history if not dry run
            if not dry_run_enabled and files:
                add_to_download_history(parsed_urls, files, form_values)

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
    shorts_summaries = list_projects(OUTPUT_DIR)
    all_project_data = aggregate_dashboard_projects(shorts_summaries)

    try:
        all_projects = [DashboardProject(**p) for p in all_project_data]
    except Exception as e:
        print(f"Error validating dashboard projects: {e}")
        print(f"Data: {all_project_data}")
        all_projects = []


    if query:
        q = query.strip().lower()
        if q:
            all_projects = [
                project
                for project in all_projects
                if q in project.id.lower()
                or q in project.title.lower()
                or (project.topic and q in project.topic.lower())
                or (project.language and q in project.language.lower())
            ]

    all_projects.sort(key=lambda p: p.updated_at or "", reverse=True)
    return all_projects


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    shorts_summaries = list_projects(OUTPUT_DIR)
    all_projects = aggregate_dashboard_projects(shorts_summaries)
    all_projects.sort(key=lambda p: p.get("updated_at"), reverse=True)

    context = {
        "request": request,
        "projects": all_projects,
    }
    return templates.TemplateResponse("dashboard.html", context)


@app.get("/translator", response_class=HTMLResponse)
async def translator_page(request: Request):
    context = {"request": request}
    return templates.TemplateResponse("translator.html", context)


@app.get("/test-simple", response_class=HTMLResponse)
async def test_simple_page(request: Request):
    context = {"request": request}
    return templates.TemplateResponse("test_simple.html", context)


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
