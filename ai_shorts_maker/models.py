"""Domain models for AI Shorts Maker editing workflows."""
from __future__ import annotations

from datetime import datetime
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field


class SubtitleLine(BaseModel):
    """Represents a single subtitle entry in the project timeline."""

    id: str
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    text: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "sub-1",
                "start": 0.0,
                "end": 4.2,
                "text": "충격적인 사건이 벌어졌습니다...",
            }
        }
    }


class TimelineSegment(BaseModel):
    """Defines media segments (video/image/audio) on the timeline."""

    id: str
    media_type: Literal["broll", "image", "audio"]
    source: str = Field(description="파일 경로 또는 가상소스 식별자")
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    extras: dict[str, Any] = Field(default_factory=dict)

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "seg-1",
                "media_type": "broll",
                "source": "auto",
                "start": 0.0,
                "end": 30.0,
                "extras": {"loop": True},
            }
        }
    }


class AudioSettings(BaseModel):
    music_enabled: bool = True
    music_volume: float = Field(default=0.12, ge=0.0, le=1.0)
    ducking: float = Field(default=0.35, ge=0.0, le=1.0)
    voice_path: str
    music_track: Optional[str] = None


class SubtitleStyle(BaseModel):
    font_size: int = Field(default=62, ge=10, le=120)
    y_offset: int = Field(default=0)
    stroke_width: int = Field(default=2, ge=0, le=10)
    font_path: Optional[str] = None
    animation: str = Field(default="none")
    template: str = Field(default="classic")
    banner_primary_text: Optional[str] = None
    banner_secondary_text: Optional[str] = None
    banner_primary_font_size: Optional[int] = None
    banner_secondary_font_size: Optional[int] = None
    banner_line_spacing: Optional[int] = None


class ProjectMetadata(BaseModel):
    base_name: str
    topic: str
    style: str
    language: str
    duration: float

    script_path: str
    audio_path: str
    subtitles_path: str
    video_path: Optional[str]
    script_text_path: Optional[str] = None

    captions: List[SubtitleLine]
    timeline: List[TimelineSegment]
    audio_settings: AudioSettings
    subtitle_style: SubtitleStyle = Field(default_factory=SubtitleStyle)

    version: int = 1
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    extra: dict[str, Any] = Field(default_factory=dict)

    model_config = {
        "json_schema_extra": {
            "example": {
                "base_name": "20250101-100000-my-topic-style-ko",
                "duration": 30.0,
                "captions": [],
                "timeline": [],
                "audio_settings": {
                    "music_enabled": True,
                    "music_volume": 0.12,
                    "ducking": 0.35,
                    "voice_path": "outputs/foo.mp3",
                },
            }
        }
    }


class ProjectSummary(BaseModel):
    base_name: str
    duration: Optional[float]
    topic: Optional[str]
    style: Optional[str]
    language: Optional[str]
    video_path: Optional[str]
    audio_path: Optional[str]
    updated_at: Optional[datetime]
    has_metadata: bool = False


class ProjectVersionInfo(BaseModel):
    version: int
    path: str
    updated_at: Optional[datetime] = None


class SubtitleCreate(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    text: str


class SubtitleUpdate(BaseModel):
    start: Optional[float] = Field(default=None, ge=0)
    end: Optional[float] = Field(default=None, gt=0)
    text: Optional[str] = None


class TimelineUpdate(BaseModel):
    segments: List[TimelineSegment]
