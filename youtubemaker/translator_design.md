# 쇼츠 번역 및 재해석기 설계서

- 작성일: 2025-09-24
- 대상 서비스: `uvicorn web_app.app:app`
- 신규 페이지: **쇼츠 번역 및 재해석기** (`/translator`)
- 연관 도구: AI 쇼츠 제작기, 유튜브 다운로드 도구 (`/ytdl`)

## 배경 및 목적

기존 AI 쇼츠 제작기는 주제 기반으로 대본부터 영상까지 자동 생성하며, 유튜브 다운로드 도구는 원본 영상과 자막을 내려받는다. 새로운 쇼츠 번역 및 재해석기는 두 도구 사이를 연결하여, 다운로드한 영상/자막을 기반으로 다국어 쇼츠(한국어, 영어, 일본어)를 빠르게 재제작하는 워크플로우를 제공한다. 주요 목적은 다음과 같다.

1. 다운로드한 영상과 자막을 그대로 활용하거나, 이미지·다른 영상 클립을 추가해 재편집한다.
2. 자막을 원하는 언어(ko/en/ja)로 번역·재해석하여 품질 높은 결과를 얻는다.
3. 번역된 스크립트로 해당 언어 TTS 음성을 생성하고, 배경음악(BGM)까지 포함한 완성본을 출력한다.

또한 홈 대시보드를 재구성하여 쇼츠 제작기·다운로더·번역기를 한 화면에서 탐색하고 진행 상태를 모니터링할 수 있도록 한다.

## 요구 사항 요약

- 유튜브 다운로드 도구에서 생성된 파일 목록을 불러와 선택 가능.
- 원본 영상을 유지하거나, 기존 AI 쇼츠 제작기의 에셋(broll, image)을 혼합 가능.
- 원본 자막을 AI로 번역/재해석; 번역 언어는 한국어/영어/일본어 중 선택.
- 번역 결과를 문장 단위로 편집 가능.
- 언어별 TTS 음성 생성 (AI 쇼츠 제작기의 TTS 파이프라인 재사용).
- 배경음악 선택 및 볼륨/덕킹 조절.
- 최종 영상은 `ai_shorts_maker.outputs` 폴더 하위에 저장하고, 프로젝트 메타데이터 관리.
- 홈 대시보드에서 새 프로젝트 생성, 검색, 진행 상태 요약 확인 기능 제공.
- 작업 상태(번역 진행, TTS 생성, 렌더링)를 UI에서 확인.
- 장기 실행 작업은 백엔드에서 비동기로 처리하고, 진행 상태 폴링.

## 목표 / 비목표

### 목표
- 다운받은 영상+자막을 입력으로 한 "번역/재해석" 전용 페이지 제공.
- 번역, 보이스오버, 배경음악, 타임라인 편집까지 단일 UI에서 수행.
- 결과물을 기존 프로젝트 구조(`ProjectMetadata`)에 맞춰 저장하여 재사용성 확보.

### 비목표
- 새로운 영상 다운로드 기능 구현 (기존 `/ytdl` 재사용).
- 완전한 비선형 편집기 구현 (간단한 구간 선택/추가 수준으로 유지).
- 다국어 UI 전체 적용 (핵심 화면은 한국어 기준, 필요시 영어 보조 텍스트 지원).

## 사용자 여정 (Happy Path)

1. `/translator` 접속 → 다운로드된 자산 목록 확인.
2. 사용할 영상/자막 세트 선택 → 기본 정보(길이, 언어) 로딩.
3. 번역 옵션 설정
   - 타깃 언어 선택 (ko/en/ja)
   - 번역 모드 (직역/요약/재해석) 슬라이더 또는 라디오 버튼
   - 참고 톤/스타일 프리셋 선택 (선택 사항)
4. "번역 실행" → AI가 문장 단위 번역본 생성 → UI에 표 형태로 표시.
5. 문장별 편집 및 타임코드 조정
   - 필요 시 문장 텍스트 수동 수정
   - 자연스러운 흐름을 위해 타임라인 구간 조정 (자막 ↔ 영상 싱크)
6. 음성 생성 설정
   - 언어별 기본 음성 추천값 자동 선택 (필요시 사용자 변경)
   - 생성 후 미리 듣기
7. 영상 구성 설정
   - 원본 영상 그대로 사용하거나 B-roll/이미지/다른 영상 추가
   - 썸네일 후보 이미지 등록(선택)
8. 배경음악 선택 및 볼륨/덕킹 설정.
9. "렌더링" 클릭 → 백엔드에서 영상 합성 → 완료 시 다운로드 링크 제공.
10. 결과 프로젝트는 AI 쇼츠 제작기 메인 페이지에서 목록으로도 확인 가능.

## 시스템 설계 개요

### 전체 흐름

```text
유튜브 다운로드 도구 → 다운로드 폴더(youtube/download)
                  ↓
쇼츠 번역 및 재해석기 (신규)
  - 소스 선택 → 번역/재해석 → 음성 생성 → 영상 구성 → 렌더링
                  ↓
AI 쇼츠 제작기 출력(assets/outputs)
```

### 홈 대시보드 구성

- `/` 라우트를 홈 대시보드로 개편하여 번역기·다운로더·쇼츠 제작기 진입점을 통합 제공한다.
- 대시보드는 `ai_shorts_maker.outputs`와 번역 프로젝트 저장소를 조회해 진행률, 최근 업데이트, 썸네일을 집계한다.
- 진행도 계산은 번역→TTS→렌더링→검수의 4단계 기준으로 `completed_steps` 값을 저장하고 UI에 ●○ 형태로 전달한다.
- 검색창은 프로젝트 메타데이터(제목, 태그, 언어)를 인덱싱한 경량 캐시를 활용해 실시간 필터링을 지원한다.
- 홈 카드 클릭 시 해당 프로젝트 유형에 맞춘 상세 페이지(/translator/{id} 또는 /?existing=)로 이동한다.

### 백엔드 구성

- `web_app/app.py`
  - 기존 `/` 라우트를 홈 대시보드 템플릿(`dashboard.html`) 렌더링으로 전환하고 프로젝트 메타데이터/진행도 컨텍스트를 주입한다.
  - 신규 라우트 추가: `/translator` (GET) → 템플릿 렌더링
  - API Router: `/api/translator/*`, `/api/dashboard/*`

- 신규 모듈 제안: `ai_shorts_maker/translator.py`
  - 자막 로딩, 번역 호출, 보이스 파일 관리, 타임라인 변환 담당
  - 기존 `services.py` / `media.py` 유틸 재사용 (특히 렌더링과 타임라인 처리)

- 번역 및 음성 합성
  - 번역: `OpenAIShortsClient` 확장 또는 래퍼 (`translate_script` 등)
  - 음성: 기존 `synthesize_voice` 재사용; 언어별 기본 voice 매핑 (예: ko→"alloy", en→"alloy", ja→"gpt-jp-voice")

- 비동기 실행
  - 번역과 렌더링은 CPU/네트워크 비용이 있음 → `run_in_threadpool` 사용
  - 상태 저장을 위한 경량 Job Store (in-memory + metadata 파일) 또는 `ProjectMetadata.extra`에 진행상태 기록

### 데이터 모델

신규 Pydantic 모델 초안:

```python
class TranslatorProjectCreate(BaseModel):
    source_video: str
    source_subtitle: str
    target_lang: Literal["ko", "en", "ja"]
    translation_mode: Literal["literal", "adaptive", "reinterpret"] = "adaptive"
    tone_hint: Optional[str] = None
    fps: Optional[int] = None
    voice: Optional[str] = None
    music_track: Optional[str] = None

class TranslatorSegment(BaseModel):
    id: str
    start: float
    end: float
    source_text: str
    translated_text: str

class TranslatorProject(BaseModel):
    id: str
    base_name: str
    status: Literal["draft", "translated", "voice_ready", "rendered", "failed"]
    source_video: str
    source_subtitle: str
    target_lang: str
    segments: list[TranslatorSegment]
    voice_path: Optional[str]
    music_track: Optional[str]
    timeline: list[TimelineSegment]
    metadata_path: str
    created_at: datetime
    updated_at: datetime
```

```python
class DashboardProjectSummary(BaseModel):
    id: str
    title: str
    project_type: Literal["shorts", "translator"]
    status: Literal["draft", "translated", "voice_ready", "rendering", "rendered", "failed"]
    completed_steps: int
    total_steps: int = 4
    thumbnail: Optional[str]
    updated_at: datetime
```

홈 대시보드는 `DashboardProjectSummary` 목록을 사용해 카드형 UI를 구성하고, 진행도(`completed_steps/total_steps`)를 시각화한다.

최종 렌더링 시 `TranslatorProject`를 `ProjectMetadata`로 변환/병합하여 기존 에디터와 호환.

### 파일 구조 변경

```
web_app/
  templates/
    dashboard.html         # 홈 대시보드 템플릿 (기존 index.html 대체)
    translator.html        # 번역/재해석기 템플릿
  static/
    dashboard.js           # 대시보드 데이터 바인딩/검색 스크립트
    translator.js          # 번역기 전용 프론트 스크립트
    dashboard.css (선택)   # 홈 대시보드 스타일 분리
    translator.css (선택)   # 번역기 스타일 분리
ai_shorts_maker/
  translator.py            # 백엔드 서비스 모듈
  outputs/
    ... 기존과 동일
youtubemaker/
  translator_design.md     # (본 문서)
```

### 외부 의존성

- 기존 OpenAI API 키 재사용 (`OpenAIShortsClient`)
- 자막 파싱: `ai_shorts_maker.subtitles`
- 영상 합성: `moviepy`
- 음성/TTS: OpenAI TTS
- 번역 품질 향상: `gpt-4o` 계열 모델 활용 (온디맨드)

## API 설계 (초안)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/` | 홈 대시보드 렌더링 (진행 중 프로젝트 요약 포함) |
| GET | `/translator` | 페이지 렌더링 |
| GET | `/api/dashboard/projects` | 홈 대시보드용 프로젝트/진행도 목록 |
| GET | `/api/translator/downloads` | `youtube/download` 폴더의 영상/자막 매칭 목록 |
| POST | `/api/translator/projects` | 번역 프로젝트 생성 (`TranslatorProjectCreate`) |
| GET | `/api/translator/projects/{id}` | 프로젝트 상세 조회 |
| PATCH | `/api/translator/projects/{id}` | 타임라인/번역텍스트/설정 업데이트 |
| POST | `/api/translator/projects/{id}/translate` | 번역 실행 (AI 호출, segments 채움) |
| POST | `/api/translator/projects/{id}/voice` | TTS 생성, 결과 경로 저장 |
| POST | `/api/translator/projects/{id}/render` | 최종 영상 렌더링 (voice + 영상 + BGM) |
| GET | `/api/translator/projects/{id}/status` | 장기 작업 상태 폴링 |
| DELETE | `/api/translator/projects/{id}` | 임시 프로젝트/산출물 삭제 |

- 다건/배치 작업을 고려해 향후 큐 시스템(예: Redis) 연동 가능성을 열어둠.

## 프론트엔드 및 UX 설계

### 홈 대시보드

- 글로벌 네비게이션과 검색이 고정된 상단 헤더를 제공해 주요 도구 접근성을 높인다.
- `새 프로젝트 +` 버튼은 모달로 번역기/쇼츠 생성 선택지를 제공하고, 선택 시 해당 폼으로 이동한다.
- 진행 중 프로젝트 카드는 `DashboardProjectSummary` 데이터를 기반으로 썸네일, 제목, 진행도(●○)를 표시한다.
- 검색 입력은 클라이언트 캐시된 프로젝트 목록을 필터링하고, 필요 시 `/api/dashboard/projects?query=`를 호출해 서버 검색을 보강한다.

```text
1. 홈 대시보드
┌────────────────────────────────────────────┐
│  [로고]   유튜브 제작기                      🔍 검색 │
├────────────────────────────────────────────┤
│  [새 프로젝트 +]                            │
│                                            │
│  진행 중 프로젝트                          │
│  ┌───────────────┐ ┌───────────────┐       │
│  │썸네일 이미지   │ │썸네일 이미지   │       │
│  │프로젝트 제목   │ │프로젝트 제목   │       │
│  │진행도 ●●○○     │ │진행도 ●●●○     │       │
│  └───────────────┘ └───────────────┘       │
│                                            │
└────────────────────────────────────────────┘
```

- 카드 클릭 시 프로젝트 유형에 맞는 상세 페이지(예: `/translator/{id}` 또는 `/` 기존 프로젝트 파라미터)로 링크한다.

### 쇼츠 번역 및 재해석기 화면

- `소스 선택 패널`: 다운로드된 파일 목록을 썸네일·길이·자막 언어와 함께 표시하고 `.mp4` + `.srt/.vtt` 페어링 기준으로 선택한다.
- `번역 옵션`: 타깃 언어 토글, 번역 모드(직역/적응/재해석), 톤 입력을 제공하고 "번역 실행" 시 로더를 표시한다.
- `번역 결과 테이블`: 타임코드·원문·번역문 3열 편집 UI로, 문장별 재번역 및 저장/취소를 제공한다.
- `음성 & 음악`: 언어별 기본 음성을 자동 제안하고, 생성된 TTS 미리 듣기와 BGM 선택/볼륨·덕킹 조절 UI를 제공한다.
- `타임라인 / 미리보기`: 원본 영상/이미지/B-roll을 재배치하고, 섬네일 캡처 버튼을 포함한 간단한 타임라인 컨트롤을 유지한다.
- `결과 다운로드`: 렌더링 진행률, 에러 로그, 완료된 다운로드 링크를 보여주며 홈 대시보드 카드와 상태가 동기화되도록 한다.

### 추가 고려사항

- 긴 문장/다국어 텍스트에 대비하기 위해 편집 테이블은 가변 행 높이와 UTF-8 렌더링을 보장한다.
- 홈 대시보드와 번역기 모두 Fetch API 기반으로 진행 상태를 폴링하며, 오류는 상단 토스트 또는 카드 상태로 노출한다.
- 접근성(키보드 네비게이션, 스크린 리더) 지원을 위해 ARIA 라벨과 포커스 순서를 명시한다.

## 음성 및 배경음악 처리

- 언어별 기본 음성 매핑 테이블 (예: `{"ko": "alloy", "en": "verse", "ja": "mizuki"}`)
- `ai_shorts_maker.media.MediaFactory.attach_audio` 재사용
- 번역된 자막으로부터 `allocate_caption_timings` 활용하여 타임라인 맞춤
- 음성 파일은 `outputs/<base_name>.mp3`로 저장, `ProjectMetadata.audio_settings.voice_path` 갱신
- BGM는 기존 `assets/music` 라이브러리 재활용, 새 트랙 업로드 기능은 차후 검토

## 테스트 전략

- 단위 테스트
  - 자막 로더: 다운로드된 자막 파싱 → `TranslatorSegment` 변환
  - 번역 함수: OpenAI 호출 모킹 후 텍스트 정합성 검증
  - 타임라인 병합: 원본 영상 길이와 번역된 타임코드 일치 여부
  - 대시보드 집계: `ProjectMetadata` + 번역 프로젝트를 `DashboardProjectSummary`로 변환하는 로직 검증

- 통합 테스트 (선택적)
  - FastAPI TestClient로 프로젝트 생성→번역→음성→렌더 API 시퀀스 검증
  - `/api/dashboard/projects` 응답이 진행도/검색 파라미터를 반영하는지 검증

- 수동 테스트
  - 실제 다운로드 파일을 활용해 다양한 언어/모드 시나리오 체크
  - 긴 영상/자막, 자막 분량 불일치, 자막 없는 경우 처리
  - 홈 대시보드 카드/검색/진행도 표시가 실시간으로 동기화되는지 확인

## 구현 단계 제안

1. **준비**
   - 다운로드 폴더 스캐너 유틸 작성 (`youtube/download` 탐색)
   - 템플릿/스타일 기본 구조 추가 (`translator.html` routing)
   - 홈 대시보드 템플릿(`dashboard.html`)과 `/api/dashboard/projects` 초안 구현

2. **데이터/모델 계층**
   - `TranslatorProject` 관련 모델 정의 및 저장 로직 (`repository` 모듈 확장 or 별도)
   - in-memory + JSON 파일 persistence 구현

3. **번역/음성 서비스 구현**
   - OpenAI 호출 래퍼 함수 작성, 재시도/에러 처리 포함
   - TTS 생성 파이프라인 연결

4. **타임라인/렌더링 통합**
   - 기존 `media.MediaFactory` 재사용, 필요시 helper 함수 추가
   - 번역 프로젝트를 `ProjectMetadata`로 변환하는 어댑터 구현

5. **프론트엔드 기능 개발**
   - fetch 기반 API 연동, 상태 표시, 편집 UI 완성
   - 음성/BGM 미리듣기 컨트롤
   - 홈 대시보드 카드/검색/진행도 UI와 번역기 상태 동기화

6. **마감**
   - 에러 메시지/로깅 개선, UX 폴리싱
   - 문서/README 업데이트

## 남은 논의 사항

- 번역 모드에 따른 프롬프트 설계 (어느 모델/템플릿 사용?)
- 긴 영상(>3분) 처리 시 성능 문제 → 클립 분할/배치 요청 전략 필요
- 사용자 업로드 지원 여부 (현재는 다운로드 파일 한정)
- 다국어 음성 라이선스/사용 권한 확인

---

본 설계서는 `youtubemaker` 기능 추가를 위한 기초 청사진으로, 구현 과정에서 발견되는 세부 사항은 추후 보완한다.
