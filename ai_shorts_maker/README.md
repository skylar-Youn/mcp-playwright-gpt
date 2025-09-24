# AI Shorts Maker

Python 기반 AI 쇼츠 제작 파이프라인입니다. 주제와 스타일을 입력하면 다음 단계를 자동화합니다.

1. OpenAI GPT 모델로 짧은 대본 작성
2. OpenAI TTS로 나레이션 음성 합성
3. 자막 타이밍 산출 및 SRT 파일 저장 (선택적으로 영상에 번인)
4. MoviePy로 배경 B-roll + 음성 + 음악을 합성하여 9:16 MP4 생성

## 준비물

- Python 3.10+
- FFmpeg (MoviePy가 호출하므로 `ffmpeg -version` 으로 확인)
- (선택) ImageMagick – `--burn-subs` 옵션으로 자막을 영상에 직접 입힐 때 필요합니다.
- OpenAI API 키 (`OPENAI_API_KEY` 환경변수)

## 설치

```bash
python -m venv .venv
source .venv/bin/activate  # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env && sed -i 's/sk-proj-.../YOUR_KEY/' .env  # 또는 수동 편집
```


기본 에셋 폴더 구조는 자동으로 생성됩니다.

```
ai_shorts_maker/
  assets/
    broll/   # 세로형 배경 영상(.mp4) 또는 이미지(.jpg) 넣기
    music/   # 배경음악(.mp3/.wav)
  outputs/   # 결과물 저장 경로
```

## 사용 예시

### 실행 명령 한눈에 보기

| 용도 | 명령어 |
| --- | --- |
| CLI로 바로 쇼츠 생성 | `python shorts_maker.py --topic "무서운 썰" --style "공포/미스터리" --duration 30 --lang ko --voice alloy` |
| FastAPI 웹 UI 실행 | `uvicorn web_app.app:app --reload` |

```bash
python shorts_maker.py \
  --topic "무서운 썰" \
  --style "공포/미스터리" \
  --duration 30 \
  --lang ko \
  --voice alloy
```

주요 옵션:

- `--fps 30` : 출력 프레임 레이트 변경
- `--no-music` : 배경음 끄기
- `--music-volume 0.18` : 배경음 볼륨 조정
- `--burn-subs` : 자막을 영상에 직접 입히기 (ImageMagick 필요)
- `--dry-run` : 스크립트/SRT만 생성하고 영상은 건너뜀
- `--save-json` : 생성 메타데이터를 JSON으로 저장

## FastAPI 웹 UI 실행

간단한 웹 인터페이스도 함께 제공합니다.

```bash
uvicorn web_app.app:app --reload
```

브라우저에서 `http://127.0.0.1:8000` 으로 접속해 주제를 입력하고 버튼 하나로 쇼츠를 만들 수 있습니다. 결과 페이지에서 생성된 MP4/MP3/SRT 파일을 바로 다운로드할 수 있습니다.
또한 기존에 만들어 둔 결과물이 있다면 상단의 드롭다운에서 선택해 곧바로 다운로드 링크를 확인할 수 있습니다.

## 출력물

`ai_shorts_maker/outputs/` 아래에 다음 파일이 생성됩니다.

- `{timestamp}-{topic}-{style}-{lang}.mp4`
- 동일한 이름의 `.mp3` (나레이션)
- 동일한 이름의 `.srt`
- (옵션) `.json` 메타데이터

샘플 배경 영상(`assets/broll/sample_broll.mp4`)과 간단한 테스트용 배경 음악(`assets/music/sample_music.wav`)을 포함해 두었습니다. 필요에 맞게 자유롭게 교체하세요.

추가 기능 (썸네일 생성, 유튜브 업로드 등)이 필요하면 코멘트 주세요!
