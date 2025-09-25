"""Repository helpers for persisting and retrieving project assets."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

from .models import ProjectMetadata, ProjectSummary, ProjectVersionInfo
from .subtitles import write_srt_from_subtitles

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).resolve().parent / "outputs"
METADATA_SUFFIX = ".metadata.json"
LEGACY_SUFFIX = ".json"


def metadata_path(base_name: str, output_dir: Optional[Path] = None) -> Path:
    directory = output_dir or OUTPUT_DIR
    return directory / f"{base_name}{METADATA_SUFFIX}"


def list_projects(output_dir: Optional[Path] = None) -> List[ProjectSummary]:
    directory = output_dir or OUTPUT_DIR
    directory.mkdir(parents=True, exist_ok=True)

    candidates: set[str] = set()
    for file in directory.glob(f"*{METADATA_SUFFIX}"):
        candidates.add(file.name[: -len(METADATA_SUFFIX)])
    for file in directory.glob(f"*{LEGACY_SUFFIX}"):
        if file.name.endswith(METADATA_SUFFIX):
            continue
        candidates.add(file.stem)
    for file in directory.glob("*.mp4"):
        candidates.add(file.stem)

    summaries: List[ProjectSummary] = []
    for base_name in sorted(candidates):
        try:
            metadata = load_project(base_name, directory)
        except FileNotFoundError:
            continue
        summaries.append(
            ProjectSummary(
                base_name=metadata.base_name,
                duration=metadata.duration,
                topic=metadata.topic,
                style=metadata.style,
                language=metadata.language,
                video_path=metadata.video_path,
                audio_path=metadata.audio_path,
                updated_at=metadata.updated_at,
                has_metadata=True,
            )
        )

    return summaries


def load_project(base_name: str, output_dir: Optional[Path] = None) -> ProjectMetadata:
    directory = output_dir or OUTPUT_DIR
    file_path = metadata_path(base_name, directory)
    data: Optional[dict[str, Any]] = None

    if file_path.exists():
        data = json.loads(file_path.read_text(encoding="utf-8"))
    else:
        legacy_path = directory / f"{base_name}{LEGACY_SUFFIX}"
        if legacy_path.exists():
            legacy_data = json.loads(legacy_path.read_text(encoding="utf-8"))
            data = legacy_data.get("metadata") if isinstance(legacy_data, dict) and "metadata" in legacy_data else legacy_data
        else:
            raise FileNotFoundError(f"Metadata file not found for {base_name}")

    if not isinstance(data, dict):
        raise FileNotFoundError(f"Invalid metadata for {base_name}")

    data.setdefault("base_name", base_name)
    data.setdefault("captions", [])
    data.setdefault("timeline", [])
    data.setdefault("extra", {})

    if "audio_settings" not in data or not isinstance(data["audio_settings"], dict):
        data["audio_settings"] = {
            "music_enabled": True,
            "music_volume": 0.12,
            "ducking": 0.35,
            "voice_path": data.get("audio_path", ""),
            "music_track": None,
        }

    if "version" not in data:
        data["version"] = 1

    if "subtitle_style" not in data or not isinstance(data["subtitle_style"], dict):
        data["subtitle_style"] = {}

    if "duration" not in data:
        captions = data.get("captions") or []
        if captions:
            try:
                data["duration"] = max(item.get("end", 0) for item in captions)
            except TypeError:
                data["duration"] = 0
        else:
            data["duration"] = 0

    return ProjectMetadata.model_validate(data)


def save_project(metadata: ProjectMetadata, output_dir: Optional[Path] = None) -> ProjectMetadata:
    directory = output_dir or OUTPUT_DIR
    directory.mkdir(parents=True, exist_ok=True)
    metadata.updated_at = datetime.utcnow()

    path = metadata_path(metadata.base_name, directory)

    if path.exists():
        try:
            old_data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            old_data = None
        if old_data:
            prev_version = old_data.get("version") or max(metadata.version - 1, 1)
            backup_dir = directory / f"{metadata.base_name}_versions"
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup_path = backup_dir / f"v{prev_version}.metadata.json"
            if not backup_path.exists():
                backup_path.write_text(
                    json.dumps(old_data, ensure_ascii=False, indent=2, default=str),
                    encoding="utf-8",
                )

    path.write_text(
        json.dumps(
            metadata.model_dump(exclude_none=False),
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    if metadata.subtitles_path:
        write_srt_from_subtitles(metadata.captions, Path(metadata.subtitles_path))

    return metadata


def delete_project(base_name: str, output_dir: Optional[Path] = None) -> None:
    directory = output_dir or OUTPUT_DIR
    metadata = load_project(base_name, directory)

    paths = [
        metadata.video_path,
        metadata.audio_path,
        metadata.subtitles_path,
        metadata.script_path,
    ]

    for value in filter(None, paths):
        file_path = Path(value)
        if file_path.exists():
            try:
                file_path.unlink()
            except OSError as exc:
                logger.warning("Failed to remove %s: %s", file_path, exc)

    metadata_file = metadata_path(base_name, directory)
    if metadata_file.exists():
        try:
            metadata_file.unlink()
        except OSError as exc:
            logger.warning("Failed to remove metadata file %s: %s", metadata_file, exc)


def list_versions(base_name: str, output_dir: Optional[Path] = None) -> List[ProjectVersionInfo]:
    directory = output_dir or OUTPUT_DIR
    versions_dir = directory / f"{base_name}_versions"
    if not versions_dir.exists():
        return []

    versions: List[ProjectVersionInfo] = []
    for file in sorted(versions_dir.glob("v*.metadata.json")):
        version_str = file.stem.lstrip("v")
        try:
            version = int(version_str)
        except ValueError:
            continue
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        updated_at_raw = data.get("updated_at")
        updated_at: Optional[datetime] = None
        if isinstance(updated_at_raw, str):
            try:
                updated_at = datetime.fromisoformat(updated_at_raw)
            except ValueError:
                updated_at = None
        versions.append(
            ProjectVersionInfo(
                version=version,
                path=str(file),
                updated_at=updated_at,
            )
        )
    return versions


def load_project_version(base_name: str, version: int, output_dir: Optional[Path] = None) -> ProjectMetadata:
    directory = output_dir or OUTPUT_DIR
    version_path = directory / f"{base_name}_versions" / f"v{version}.metadata.json"
    if not version_path.exists():
        raise FileNotFoundError(f"Version {version} for {base_name} not found")
    data = json.loads(version_path.read_text(encoding="utf-8"))
    return ProjectMetadata.model_validate(data)


def clone_project(base_name: str, output_dir: Optional[Path] = None) -> ProjectMetadata:
    """프로젝트를 복제하여 백업본을 생성합니다."""
    import shutil
    from datetime import datetime
    from uuid import uuid4

    directory = output_dir or OUTPUT_DIR

    # 원본 프로젝트 로드
    original_project = load_project(base_name, directory)

    # 새 프로젝트 이름 생성 (백업_원본이름_타임스탬프)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    clone_name = f"backup_{base_name}_{timestamp}"

    # 프로젝트 메타데이터 복제
    cloned_project = ProjectMetadata.model_validate(original_project.model_dump())
    cloned_project.base_name = clone_name
    cloned_project.created_at = datetime.utcnow()
    cloned_project.updated_at = datetime.utcnow()

    # 파일들 복제
    file_paths = [
        ("video_path", original_project.video_path),
        ("audio_path", original_project.audio_path),
        ("subtitles_path", original_project.subtitles_path),
        ("script_path", original_project.script_path),
    ]

    for field_name, original_path in file_paths:
        if original_path and Path(original_path).exists():
            original_file = Path(original_path)
            # 새 파일명 생성
            new_filename = f"{clone_name}{original_file.suffix}"
            new_path = directory / new_filename

            # 파일 복사
            shutil.copy2(original_file, new_path)

            # 메타데이터의 경로 업데이트
            setattr(cloned_project, field_name, str(new_path))

    # 복제된 프로젝트 저장
    return save_project(cloned_project, directory)
