# AI Shorts Maker 확장 설계 문서

## 1. 현재 시스템 개요

- **언어/런타임**: Python 3.11, MoviePy 2.x, FastAPI, OpenAI SDK.
- **핵심 패키지(`ai_shorts_maker`)**
  - `generator.py`: 스크립트 생성 → TTS → 자막 → 영상 합성 전체 워크플로 담당.
  - `media.py`: B-roll/배경 이미지/배경음/자막 번인을 처리하는 미디어 조립 유틸.
  - `openai_client.py`: GPT, TTS 호출 래퍼.
  - `subtitles.py`: 문장 분리, 타이밍 분배, SRT 파일 생성 유틸.
- **CLI 진입점**: `shorts_maker.py` → `ai_shorts_maker.cli`.
- **웹 앱(`web_app`)**
  - FastAPI + Jinja 템플릿. 현재는 단일 폼 + 생성 결과 다운로드 UI.
  - `outputs/` 디렉터리를 스캔해 기존 결과를 목록에 노출.
- **파일 구조**
  - `assets/broll`, `assets/music`: 사용자가 직접 넣는 원천 미디어.
  - `outputs/`: `{timestamp}-{topic}-{style}-{lang}.*` 네이밍으로 결과 저장.

## 1.1 구현 현황 요약 (2025-02)

- `ai_shorts_maker/models.py`에 Pydantic 도메인 모델 정의 (프로젝트, 자막, 타임라인, 오디오 설정).
- `ai_shorts_maker/repository.py`/`services.py`가 프로젝트 메타데이터 CRUD와 자막·타임라인·오디오 편집 로직을 제공.
- FastAPI 라우터(`/api/projects/...`)로 자막 추가·수정·삭제, 타임라인/오디오 업데이트, 프로젝트 삭제 API 구현.
- 웹 UI(`web_app/templates/index.html`)가 자막 인라인 편집, 타임라인 JSON 수정, 오디오 파라미터 조정 등 기본 편집 기능을 수행.
- 프로젝트 생성 시 `.metadata.json`을 포함한 메타데이터가 자동 생성·동기화되어 SRT와 일관성을 유지.
- `/api/projects/{base_name}/render`가 메타데이터 기반으로 영상을 재합성하며 버전 넘버가 자동 증가(백업 보존).
- wavesurfer.js 기반 타임라인 시각화와 버전 히스토리/롤백 UI가 제공되어 변경 추적 및 복원이 가능.
- 타임라인 세그먼트에서 오버레이 이미지/영상의 시작·종료 위치, 스케일, 알파를 지정해 간단한 모션 효과(수동 키프레임 + 자동 Ken Burns/줌/팬 프리셋)를 줄 수 있고, 자막 폰트 크기/세로 위치/외곽선 두께, 애니메이션(슬라이드 등)도 UI에서 바로 조정 후 재렌더링으로 반영됩니다.

## 2. 요구 기능 정리

1. **기존 결과 불러오기**
   - 영상/음성/자막 파일을 선택해 미리보기 및 편집 시작.
2. **자막 편집 (추가/수정/삭제)**
   - 텍스트 수정, 구간 분할/병합, 시간 조정.
   - 변경사항은 라이브 미리보기/저장에 반영.
3. **미디어 정렬(타임라인 맞춤)**
   - 음성·배경음·이미지(B-roll)의 재생 위치를 조정.
   - 타임라인 기반 UI에서 키프레임 또는 슬라이더로 조작.
4. **재생/미리보기**
   - 특정 시간 구간을 재생하며 편집 결과 확인.
5. **삭제/버전 관리**
   - 불필요한 결과물 삭제, 편집 히스토리 또는 버전 태깅.

## 3. 제안 아키텍처 개요

### 3.1 레이어 구조

| 레이어 | 책임 | 구현 방향 |
| --- | --- | --- |
| Presentation | FastAPI 라우터, Jinja 템플릿, 향후 React/Vue 등 SPA 고려 | `/web_app/app.py` 분리 → `routers`, `services` 구조화 |
| Application Service | 비즈니스 로직 (편집 워크플로, 파일 관리) | `services/assets.py`, `services/editor.py` 등 신설 |
| Domain/Model | 메타데이터, 타임라인, subtitle 엔티티 | Pydantic 모델 정의 (`models/metadata.py`, `models/timeline.py`) |
| Infrastructure | 파일 시스템 접근, OpenAI API, MoviePy 파이프라인 | 기존 `ai_shorts_maker` 재사용, 저장소 인터페이스 제공 |

### 3.2 주요 컴포넌트

1. **AssetRepository**
   - `outputs/` 스캔, 파일 CRUD, 버전 디렉터리 관리.
   - 메타데이터 JSON/SRT 파싱 → Python 객체화.
2. **EditingService**
   - 자막/타임라인 편집 API 제공.
   - 오디오 길이 기반의 자동 정렬 로직 포함.
3. **PreviewService**
   - 특정 시점의 썸네일 생성, 음성 파형 데이터 추출.
   - 빠른 재생을 위해 저해상도 HLS/MP4 임시 파일 생성.
4. **RenderService**
   - 편집 결과를 다시 MoviePy로 렌더링.
   - 변경된 자막/타임라인을 반영.

## 4. UI & 워크플로 시나리오

### 4.1 불러오기
1. `/outputs` API → 결과 목록 가져오기.
2. 사용자가 항목 선택 시
   - 메타데이터(JSON) + SRT + mp3 + mp4 경로를 응답.
   - 프론트는 메타데이터를 상태로 저장, 자막 리스트 랜더링.

### 4.2 자막 편집 플로우
1. 리스트/테이블에 각 자막 항목 표시 (start, end, text).
2. 편집 조작
   - **텍스트**: 인라인 편집 후 `PATCH /subtitles/{id}` 호출.
   - **시간 조정**: 드래그/입력 → 시작/종료 업데이트, 인접 구간 자동 보정.
   - **추가/삭제**: `POST`, `DELETE` 엔드포인트.
3. 저장 시 서버는 SRT/메타데이터 파일을 갱신 → 버전 넘버 증가.
4. 즉시 미리보기 업데이트를 위해 웹소켓/폴링으로 변경 사항 통지.

### 4.3 타임라인 정렬
1. 오디오 파형 + 썸네일을 그리는 타임라인 컴포넌트(예: wavesurfer.js + custom overlay).
2. 음성(mp3)과 B-roll 구간을 서로 다른 트랙으로 시각화.
3. 사용자가 B-roll 시점/길이를 조정하면 `PATCH /timeline/broll` 호출.
4. 배경음 볼륨/덕킹도 동일 서비스에서 매개변수로 관리.

### 4.4 재생 미리보기
- 브라우저에서 `<video>` 태그로 mp4 재생.
- 편집 중에는 `GET /preview?time=...` 으로 특정 구간만 빠르게 재인코딩 → HLS 세그먼트 생성 고려.

### 4.5 최근 UI 확장 사항
- wavesurfer.js 기반 파형을 표시하고, 세그먼트 오버레이를 통해 드래그 없이도 세그먼트 선택/이동이 가능하도록 구성했습니다.
- 세그먼트 편집 폼과 "세그먼트 추가/삭제" 기능을 통해 시간/소스/타입을 실시간 수정하고 저장 전에 미리 조정할 수 있습니다.
- 버전 히스토리 패널에서 저장된 메타데이터 백업을 목록화하고, 선택 즉시 `/api/projects/{base}/versions/{version}/restore` 호출로 롤백할 수 있습니다.
- 재렌더 버튼은 `/api/projects/{base}/render`를 연결해 편집을 반영한 영상을 즉시 재생성하며, 필요 시 자막 번인 옵션을 포함합니다.

## 5. 데이터 모델 제안

### 5.1 메타데이터 스키마 (Pydantic 예시)
```python
class TimelineSegment(BaseModel):
    media_type: Literal["broll", "image", "audio", "subtitle"]
    source: str
    start: float
    end: float
    extra: dict[str, Any] = {}

class SubtitleLine(BaseModel):
    id: str
    start: float
    end: float
    text: str

class ProjectMetadata(BaseModel):
    base_name: str
    topic: str
    style: str
    language: str
    duration: float
    subtitles: list[SubtitleLine]
    timeline: list[TimelineSegment]
    audio_settings: dict[str, Any]
    version: int = 1
    created_at: datetime
    updated_at: datetime
```

### 5.2 파일 저장 전략
- 결과 디렉터리에 `metadata.json`, `subtitles.srt`, `project.yaml` 등을 동봉.
- 편집 시 `version-N/` 하위 폴더에 백업을 남겨 롤백 지원.

## 6. API 설계 (초안)

| Method | Path | 설명 |
| --- | --- | --- |
| `GET` | `/api/projects` | 기존 결과 목록, 썸네일/길이 포함 |
| `GET` | `/api/projects/{base_name}` | 메타데이터+파일 경로 반환 |
| `POST` | `/api/projects/{base_name}/subtitles` | 자막 추가 |
| `PATCH` | `/api/projects/{base_name}/subtitles/{id}` | 자막 수정 (텍스트, 시간) |
| `DELETE` | `/api/projects/{base_name}/subtitles/{id}` | 자막 삭제 |
| `PATCH` | `/api/projects/{base_name}/timeline` | B-roll/이미지/음성 구간 조정 |
| `POST` | `/api/projects/{base_name}/render` | 편집 반영한 새 영상 렌더링 |
| `DELETE` | `/api/projects/{base_name}` | 프로젝트 전체 삭제 |

- **응답 형식**: `application/json`, 성공 시 최신 메타데이터 반환.
- **권장 검증**: Pydantic DTO로 필드 검증, 중첩 시간 충돌 검사.

## 7. 프런트엔드 UI 설계 제안

1. **레이아웃**
   - 좌측: 프로젝트 목록
   - 중앙: 비디오 플레이어 + 타임라인 (음성/자막/이미지 트랙)
   - 우측: 자막 편집 패널, 속성 조절 슬라이더
2. **타임라인 컴포넌트**
   - wavesurfer.js로 음성 파형 렌더 → 자막/이미지 트랙은 캔버스/React component로 오버레이.
   - 드래그·드롭으로 구간 이동, 핸들로 길이 조정.
3. **자막 편집**
   - 데이터 그리드(Handsontable/SlickGrid 등)로 구현, 다중 선택 / 단축키 지원.
   - 변경 시 실시간 검증 (겹침, 음수 시간 방지).
4. **미리보기**
   - `<video>` 태그 + currentTime 연동.
   - 특정 자막 클릭 → 해당 시점으로 시킹.
5. **삭제/버전관리**
   - "이전 버전 복원" 버튼, `version` 히스토리 모달.

## 8. 향후 고려 사항

- **퍼포먼스**: 긴 영상 편집 시 MoviePy 재렌더링 부담 → FFmpeg 직접 호출, HLS 세그먼트 생성 고려.
- **동시성**: 여러 사용자가 동일 프로젝트를 편집하는 경우
  - 파일 락킹 or optimistic locking (버전 비교) 필요.
- **서버 저장소**: 용량 증가 대비 주기적 클린업 배치.
- **테스트**: API 레벨 pytest, UI 레벨 Playwright E2E 구축 권장.
- **보안**: API 키/자격정보는 `.env`에 별도 관리, 템플릿에서 노출 금지.

---
이 문서는 현재 구조를 이해한 뒤, 자막/음성/영상의 불러오기·편집·정렬 기능을 단계적으로 확장할 때 참고할 수 있는 기본 설계 초안입니다. 우선순위 및 세부 구현은 실제 요구 사항과 인력 구성에 맞춰 세부화하세요.
