# video-dub

**English** · [中文](README.zh.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Deutsch](README.de.md) · [Français](README.fr.md) · [Español](README.es.md) · [العربية](README.ar.md)

---

Dub any MP4 video into another language with:

- **ASR transcription** — faster-whisper (runs fully offline)
- **LLM translation** — Claude or GPT, business register, concise
- **Neural TTS** — edge-tts (400+ voices, no API key needed)
- **Per-segment freeze-frame sync** — if TTS overruns the original clip, the video holds its last frame instead of cascading drift
- **Soft subtitles** — `mov_text` stream, toggleable in QuickTime / VLC / mpv

---

## Requirements

| Tool | Version | Install |
|------|---------|---------|
| Python | ≥ 3.10 | [python.org](https://www.python.org) |
| ffmpeg + ffprobe | ≥ 5.0 | `brew install ffmpeg` / `apt install ffmpeg` |
| ANTHROPIC_API_KEY | — | for Claude translation |
| OPENAI_API_KEY | — | for GPT translation (alternative) |

---

## Installation

```bash
git clone <this-repo> video-dub
cd video-dub
bash install.sh
```

`install.sh` creates a `.venv/` and installs all Python dependencies.

---

## Quick start

```bash
# Set your API key
export ANTHROPIC_API_KEY=sk-ant-...

# Full pipeline in one command
.venv/bin/python3 pipeline.py \
  --video  /path/to/source.mp4 \
  --lang   ja \
  --voice  ja-JP-NanamiNeural \
  --out    /path/to/source_ja.mp4
```

The output MP4 is a fully dubbed video with:
- Stream 0: original H.264 video (with freeze frames where needed)
- Stream 1: Japanese AAC audio (NanamiNeural @ +15% rate)
- Stream 2: Japanese soft subtitle (mov_text)

---

## Step-by-step usage

Run each step independently to inspect intermediate results:

```bash
# Step 1 — Transcribe (produces transcript_en.json)
python3 steps/transcribe.py \
  --video  source.mp4 \
  --model  medium \
  --out    work/transcript_en.json

# Step 2 — Translate (produces transcript_ja.json)
python3 steps/translate.py \
  --input      work/transcript_en.json \
  --lang       ja \
  --translator claude \
  --out        work/transcript_ja.json

# Step 3 — Synthesize TTS (produces work/tts_segments/seg_*.mp3)
python3 steps/synthesize.py \
  --transcript work/transcript_ja.json \
  --voice      ja-JP-NanamiNeural \
  --rate       "+15%" \
  --out-dir    work/tts_segments/

# Step 4 — Assemble (produces video_joined.mp4, audio_joined.wav, subtitles.srt)
python3 steps/assemble.py \
  --video      source.mp4 \
  --transcript work/transcript_ja.json \
  --tts-dir    work/tts_segments/ \
  --out-dir    work/assembled/

# Step 5 — Mux (produces final MP4)
python3 steps/mux.py \
  --video  work/assembled/video_joined.mp4 \
  --audio  work/assembled/audio_joined.wav \
  --srt    work/assembled/subtitles.srt \
  --lang   ja \
  --out    source_ja.mp4
```

---

## Resume / skip flags

```bash
# Skip transcription (supply pre-existing JSON)
python3 pipeline.py --video source.mp4 \
  --transcript work/transcript_en.json \
  --lang ja --out output.mp4

# Skip transcription + translation
python3 pipeline.py --video source.mp4 \
  --translated work/transcript_ja.json \
  --out output.mp4

# Skip transcription + translation + TTS
python3 pipeline.py --video source.mp4 \
  --translated work/transcript_ja.json \
  --tts-dir work/tts_segments/ \
  --out output.mp4
```

---

## Key options

| Flag | Default | Description |
|------|---------|-------------|
| `--lang` | `ja` | Target language BCP-47 code |
| `--voice` | `ja-JP-NanamiNeural` | edge-tts voice |
| `--rate` | `+15%` | Speech rate; +15% = professional presenter pace |
| `--whisper-model` | `medium` | `tiny` fastest ↔ `large-v3` most accurate |
| `--translator` | `claude` | `claude` / `openai` / `none` |
| `--style` | *(auto)* | Register hint in translation prompt |
| `--crf` | `22` | x264 quality (18=high, 28=small file) |
| `--work-dir` | `<stem>_dub_work/` | Intermediates directory |

---

## How the assembly works

```
for each segment i:
  window  = segs[i+1].start − segs[i].start
  overrun = max(0, tts_duration − window)

  ┌─────────────────────────────────────┐
  │  VIDEO:  original clip (window sec) │
  │          + freeze last frame        │  ← only if overrun > 0
  │            (overrun sec)            │
  └─────────────────────────────────────┘
  ┌─────────────────────────────────────┐
  │  AUDIO:  TTS (tts_duration sec)     │
  │          + silence                  │  ← only if overrun == 0
  │            (window − tts_dur sec)   │
  └─────────────────────────────────────┘

  SRT cue: output_start → output_start + tts_duration
```

This eliminates the cascade-drift problem of sequential start-alignment. Each segment is self-contained: its video window either plays naturally (with silence) or extends via freeze frame, and the subtitle timing is recomputed on the output timeline.

---

## Voice reference

Run `edge-tts --list-voices` to see all 400+ voices. Common choices:

| Language | Female | Male |
|----------|--------|------|
| Japanese | `ja-JP-NanamiNeural` | `ja-JP-KeitaNeural` |
| Chinese | `zh-CN-XiaoxiaoNeural` | `zh-CN-YunxiNeural` |
| Korean | `ko-KR-SunHiNeural` | `ko-KR-InJoonNeural` |
| English (US) | `en-US-JennyNeural` | `en-US-GuyNeural` |
| Spanish | `es-ES-ElviraNeural` | `es-ES-AlvaroNeural` |
| French | `fr-FR-DeniseNeural` | `fr-FR-HenriNeural` |
| German | `de-DE-KatjaNeural` | `de-DE-ConradNeural` |

---

## Using inside Claude Code

Copy `SKILL.md` to `.claude/agents/video-dub.md` in your project:

```bash
cp SKILL.md /your/project/.claude/agents/video-dub.md
```

Then in Claude Code, say:
> "Dub `/path/to/source.mp4` into Japanese with business tone."

Claude will read the skill, resolve paths, and run `pipeline.py` automatically.

## Using inside IBM Bob / Codex / other LLM tools

The `SKILL.md` file is a self-contained LLM instruction document. Point your tool at it:

- **IBM Bob**: add to your skills/instructions directory as `video-dub.md`
- **Codex / GPT-4**: include `SKILL.md` content in your system prompt or project instructions
- **Generic**: any LLM that can read files and execute shell commands can follow SKILL.md

---

## Project layout

```
video_dub/
├── SKILL.md          LLM skill entry point
├── README.md         this file
├── requirements.txt  Python deps
├── install.sh        one-time setup
├── pipeline.py       all-in-one runner
└── steps/
    ├── transcribe.py Step 1: faster-whisper ASR
    ├── translate.py  Step 2: LLM translation (Claude / OpenAI)
    ├── synthesize.py Step 3: edge-tts TTS synthesis
    ├── assemble.py   Step 4: per-segment video+audio+SRT
    └── mux.py        Step 5: final MP4 mux
```

---

## License

Apache 2.0
