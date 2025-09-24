# ytdl.py 사용법

ytdl.py는 yt-dlp를 감싼 간단한 CLI 스크립트로, 유튜브 영상과 자막을 한 번에 내려받을 수 있습니다.

## 사전 준비
- Python 3.11 이상
- 프로젝트 의존성 설치: `python3 -m pip install -r ../requirements.txt`

## 기본 다운로드
```bash
python3 ytdl.py <유튜브-URL>
```
- 영상과 자막 파일은 기본적으로 `youtube/download/"<제목> [<영상ID>].<확장자>"` 형태로 저장됩니다.

## 주요 옵션
- `-o, --output-dir 경로` : 저장할 디렉터리를 지정합니다. (기본값: `youtube/download`)
- `--dry-run` : 실제 다운로드 없이 어떤 파일이 생성될지 미리 확인합니다.
- `--sub-langs 언어코드들` : 자막 언어를 콤마로 구분해 지정합니다. 기본값은 `all`로 제공되는 모든 자막을 받습니다.
- `--sub-format 형식` : 자막 파일 형식을 지정합니다. 기본값은 `best`입니다.
- `--no-subs` : 자막 다운로드를 건너뜁니다.
- `--no-auto-subs` : 자동 생성(기계 번역) 자막은 제외하고, 업로드된 자막만 받습니다.

## 사용 예시
영상과 모든 자막을 특정 폴더로 저장:
```bash
python3 ytdl.py "https://www.youtube.com/watch?v=dQw4w9WgXcQ" \
  --output-dir /tmp/ytdl_downloads
```

영상을 다운로드하지 않고, 영어 자막만 미리 확인:
```bash
python3 ytdl.py "https://www.youtube.com/watch?v=dQw4w9WgXcQ" \
  --dry-run --sub-langs en
```

영상과 영어·일본어 자막을 함께 저장:
```bash
python3 ytdl.py "https://www.youtube.com/watch?v=dQw4w9WgXcQ" \
  --sub-langs en,ja,ko
```

python3 ytdl.py "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --sub-langs ko

python3 ytdl.py "https://www.youtube.com/shorts/4y6uaG2UZ9E" --sub-langs ko

## 참고 사항
- `--no-auto-subs` 옵션을 주지 않으면 자동 생성 자막도 함께 내려받습니다.
- yt-dlp는 동일한 파일이 이미 존재하면 재사용합니다. 새로 받으려면 기존 파일을 삭제하세요.
- 고급 포맷 선택이 필요하면 `yt-dlp --help`를 참고하거나, 필요한 옵션을 환경 변수 `YT_DLP_ACCESS_ARGS`에 추가해 사용할 수 있습니다.

## 웹 UI 활용
- FastAPI 앱(`uvicorn web_app.app:app --reload`)을 실행하면 `/ytdl` 경로에서 간단한 폼 기반 UI로 영상/자막 다운로드를 제어할 수 있습니다.
- 한 번에 여러 URL을 줄바꿈으로 넣고, 자막 언어·드라이런 여부 등을 체크박스와 입력란으로 지정할 수 있습니다.
