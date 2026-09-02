# video-dub

모든 MP4 동영상을 다른 언어로 더빙합니다.

- **ASR 음성 인식** — faster-whisper（완전 오프라인 동작）
- **LLM 번역** — Claude 또는 GPT 기반의 비즈니스 격식체 번역
- **신경망 TTS** — edge-tts（400개 이상의 음성, API Key 불필요）
- **세그먼트별 프리즈 프레임 동기화** — TTS가 원본 세그먼트 시간 창을 초과하면 마지막 프레임에서 영상을 정지하여 연쇄 오프셋 방지
- **소프트 자막** — `mov_text` 스트림（QuickTime / VLC / mpv에서 자유롭게 켜고 끌 수 있음）

---

## 요구 사항

| 도구 | 버전 | 설치 방법 |
|------|------|----------|
| Python | ≥ 3.10 | [python.org](https://www.python.org) |
| ffmpeg + ffprobe | ≥ 5.0 | `brew install ffmpeg` / `apt install ffmpeg` |
| ANTHROPIC_API_KEY | — | Claude 번역에 필요 |
| OPENAI_API_KEY | — | GPT 번역에 필요（대안） |

---

## 설치

```bash
git clone <저장소 URL> video-dub
cd video-dub
bash install.sh
```

`install.sh`가 `.venv/` 가상 환경을 생성하고 모든 Python 의존성을 설치합니다.

---

## 빠른 시작

```bash
# API Key 설정
export ANTHROPIC_API_KEY=sk-ant-...

# 한 명령으로 전체 파이프라인 실행
.venv/bin/python3 pipeline.py \
  --video  /path/to/source.mp4 \
  --lang   ko \
  --voice  ko-KR-SunHiNeural \
  --out    /path/to/source_ko.mp4
```

출력 MP4에는 다음 스트림이 포함됩니다：
- 스트림 0：H.264 영상（프리즈 프레임 포함）
- 스트림 1：한국어 AAC 오디오（SunHiNeural @ +15% 속도）
- 스트림 2：한국어 소프트 자막（mov_text）

---

## 단계별 실행

각 단계를 개별적으로 실행하여 중간 결과물을 확인할 수 있습니다：

```bash
# Step 1 — 음성 인식（transcript_en.json 생성）
python3 steps/transcribe.py \
  --video  source.mp4 \
  --model  medium \
  --out    work/transcript_en.json

# Step 2 — 번역（transcript_ko.json 생성）
python3 steps/translate.py \
  --input      work/transcript_en.json \
  --lang       ko \
  --translator claude \
  --out        work/transcript_ko.json

# Step 3 — TTS 합성（work/tts_segments/seg_*.mp3 생성）
python3 steps/synthesize.py \
  --transcript work/transcript_ko.json \
  --voice      ko-KR-SunHiNeural \
  --rate       "+15%" \
  --out-dir    work/tts_segments/

# Step 4 — 어셈블（video_joined.mp4, audio_joined.wav, subtitles.srt 생성）
python3 steps/assemble.py \
  --video      source.mp4 \
  --transcript work/transcript_ko.json \
  --tts-dir    work/tts_segments/ \
  --out-dir    work/assembled/

# Step 5 — 먹싱（최종 MP4 생성）
python3 steps/mux.py \
  --video  work/assembled/video_joined.mp4 \
  --audio  work/assembled/audio_joined.wav \
  --srt    work/assembled/subtitles.srt \
  --lang   ko \
  --out    source_ko.mp4
```

---

## 중간 재개

```bash
# 음성 인식 건너뛰기（기존 JSON 사용）
python3 pipeline.py --video source.mp4 \
  --transcript work/transcript_en.json \
  --lang ko --out output.mp4

# 음성 인식 + 번역 건너뛰기
python3 pipeline.py --video source.mp4 \
  --translated work/transcript_ko.json \
  --out output.mp4

# 음성 인식 + 번역 + TTS 건너뛰기
python3 pipeline.py --video source.mp4 \
  --translated work/transcript_ko.json \
  --tts-dir work/tts_segments/ \
  --out output.mp4
```

---

## 주요 옵션

| 플래그 | 기본값 | 설명 |
|--------|--------|------|
| `--lang` | `ja` | 대상 언어 코드（BCP-47） |
| `--voice` | `ja-JP-NanamiNeural` | edge-tts 음성 이름 |
| `--rate` | `+15%` | 발화 속도；+15%는 전문 내레이터 페이스 |
| `--whisper-model` | `medium` | `tiny`（빠름） ↔ `large-v3`（정확） |
| `--translator` | `claude` | `claude` / `openai` / `none` |
| `--style` | *(자동)* | 번역 어조 프롬프트 |
| `--crf` | `22` | x264 품질（18=고화질, 28=소용량） |
| `--work-dir` | `<stem>_dub_work/` | 중간 파일 저장 디렉토리 |

---

## 어셈블 알고리즘

```
각 세그먼트 i에 대해：
  window  = segs[i+1].start − segs[i].start
  overrun = max(0, TTS 길이 − window)

  ┌─────────────────────────────────────┐
  │  영상：원본 클립（window 초）        │
  │        + 마지막 프레임 정지         │  ← overrun > 0일 때만
  │          （overrun 초）             │
  └─────────────────────────────────────┘
  ┌─────────────────────────────────────┐
  │  오디오：TTS（TTS 길이 초）         │
  │          + 무음                     │  ← overrun = 0일 때만
  │            （window − TTS 길이 초） │
  └─────────────────────────────────────┘

  자막 타임코드 = 출력 타임라인 누적 위치
```

각 세그먼트가 완전히 독립적으로 처리되므로 연쇄 오프셋이 발생하지 않습니다.

---

## 음성 참고

`edge-tts --list-voices`로 400개 이상의 음성을 확인하세요：

| 언어 | 여성 | 남성 |
|------|------|------|
| 일본어 | `ja-JP-NanamiNeural` | `ja-JP-KeitaNeural` |
| 중국어（보통화） | `zh-CN-XiaoxiaoNeural` | `zh-CN-YunxiNeural` |
| 한국어 | `ko-KR-SunHiNeural` | `ko-KR-InJoonNeural` |
| 영어（미국） | `en-US-JennyNeural` | `en-US-GuyNeural` |
| 스페인어 | `es-ES-ElviraNeural` | `es-ES-AlvaroNeural` |
| 프랑스어 | `fr-FR-DeniseNeural` | `fr-FR-HenriNeural` |
| 독일어 | `de-DE-KatjaNeural` | `de-DE-ConradNeural` |

---

## Claude Code에서 사용하기

`SKILL.md`를 프로젝트의 `.claude/agents/` 디렉토리에 복사하세요：

```bash
cp SKILL.md /your/project/.claude/agents/video-dub.md
```

Claude Code에서 다음과 같이 요청하면 됩니다：
> "`/path/to/source.mp4`를 비즈니스 어투의 한국어로 더빙해 주세요."

Claude가 스킬 파일을 읽고 경로를 파악하여 `pipeline.py`를 자동으로 실행합니다.

---

## 프로젝트 구조

```
video_dub/
├── SKILL.md          LLM 스킬 진입점
├── README.md         영어 문서
├── README.ko.md      본 문서
├── requirements.txt  Python 의존성
├── install.sh        설치 스크립트
├── pipeline.py       전체 파이프라인 실행
└── steps/
    ├── transcribe.py Step 1：faster-whisper ASR
    ├── translate.py  Step 2：LLM 번역
    ├── synthesize.py Step 3：edge-tts TTS 합성
    ├── assemble.py   Step 4：세그먼트별 어셈블（핵심）
    └── mux.py        Step 5：최종 먹싱
```

---

## 라이선스

Apache 2.0
