# video-dub Skill

Dub any MP4 video into another language with per-segment freeze-frame alignment,
neural TTS synthesis, and auto-synced soft subtitles.

## What this skill does

1. **Transcribe** — faster-whisper extracts per-segment timestamps from the source video
2. **Translate** — LLM rewrites each segment in the target language (business register, concise)
3. **Synthesize** — edge-tts generates MP3 per segment at a uniform speech rate
4. **Assemble** — for each segment:
   - if TTS fits inside the original window → play TTS + fill remainder with silence
   - if TTS overruns the window → extend that video segment with a freeze frame of its last frame
5. **Mux** — merge the rebuilt video track, the new audio track, and a soft `mov_text` subtitle stream

## Skill directory layout

```
video_dub/
├── SKILL.md          ← this file (LLM entry point)
├── README.md         ← human installation / usage guide
├── requirements.txt  ← Python dependencies
├── install.sh        ← one-time environment setup
├── pipeline.py       ← all-in-one runner
└── steps/
    ├── transcribe.py ← Step 1
    ├── translate.py  ← Step 2
    ├── synthesize.py ← Step 3
    ├── assemble.py   ← Step 4
    └── mux.py        ← Step 5
```

## Prerequisites

**System (must be on PATH):**
- `ffmpeg` ≥ 5.0 with libx264
- `ffprobe` (ships with ffmpeg)
- Python ≥ 3.10

**Python (installed by `install.sh`):**
- `faster-whisper`
- `edge-tts`
- `anthropic` (for Claude translation) **or** `openai` (for GPT translation)

**API key (set in environment):**
- `ANTHROPIC_API_KEY` — if using Claude for translation
- `OPENAI_API_KEY` — if using OpenAI GPT for translation
- Neither needed if `--skip-translate` is used with a pre-translated JSON

## Invocation

### Full pipeline (one command)

```bash
python3 pipeline.py \
  --video  /path/to/source.mp4 \
  --lang   ja \
  --voice  ja-JP-NanamiNeural \
  --rate   "+15%" \
  --out    /path/to/source_ja.mp4
```

### Step-by-step (for inspection between steps)

```bash
# Step 1 — transcribe
python3 steps/transcribe.py --video source.mp4 --out work/transcript_en.json

# Step 2 — translate  (or supply your own translated JSON and skip this)
python3 steps/translate.py \
  --input  work/transcript_en.json \
  --lang   ja \
  --style  "敬語・ですます体" \
  --out    work/transcript_ja.json

# Step 3 — synthesize TTS
python3 steps/synthesize.py \
  --transcript work/transcript_ja.json \
  --voice ja-JP-NanamiNeural \
  --rate  "+15%" \
  --out-dir work/tts_segments/

# Step 4 — assemble (video segments + audio segments + SRT)
python3 steps/assemble.py \
  --video      source.mp4 \
  --transcript work/transcript_ja.json \
  --tts-dir    work/tts_segments/ \
  --out-dir    work/assembled/

# Step 5 — mux
python3 steps/mux.py \
  --video   work/assembled/video_joined.mp4 \
  --audio   work/assembled/audio_joined.wav \
  --srt     work/assembled/subtitles.srt \
  --lang    jpn \
  --out     source_ja.mp4
```

## Key parameters

| Parameter | Default | Notes |
|-----------|---------|-------|
| `--lang` | `ja` | BCP-47 target language code |
| `--voice` | `ja-JP-NanamiNeural` | Any edge-tts voice name |
| `--rate` | `+15%` | Speech rate offset; +15% = natural professional pace |
| `--whisper-model` | `medium` | `tiny` / `base` / `small` / `medium` / `large-v3` |
| `--translator` | `claude` | `claude` / `openai` / `none` (use pre-translated JSON) |
| `--style` | *(language-specific default)* | Prompt fragment for register/tone |
| `--crf` | `22` | x264 CRF for re-encoded segments (18=high quality, 28=small) |

## Assembly logic (Step 4 detail)

```
for each segment i:
  window  = segs[i+1].start − segs[i].start   # (or video_end for last seg)
  overrun = max(0, tts_dur − window)

  video clip = original[segs[i].start : segs[i].start + window]
  if overrun > 0:
      video clip += freeze_last_frame(overrun seconds)   # tpad filter
  
  audio clip = tts_seg_i.wav
  if overrun == 0:
      audio clip += silence(window − tts_dur)

  subtitle cue: starts at cumulative output start, ends at start + tts_dur
```

Total output duration = Σ max(window_i, tts_dur_i)

## LLM workflow (when run inside Claude Code / IBM Bob / Codex)

When the user requests video dubbing:

1. Read this SKILL.md
2. Confirm: source video path, target language, desired voice/rate
3. Run `install.sh` once if not already done
4. Run `pipeline.py` with the resolved arguments, streaming progress to the user
5. Report the output path and duration

For the translation step, if `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` is not set,
perform the translation directly using the host LLM's capabilities:
- Read `work/transcript_en.json`
- Translate each segment respecting the segment count and JSON structure
- Write the result to `work/transcript_{lang}.json`
- Pass `--skip-translate --translated work/transcript_{lang}.json` to subsequent steps

## Supported target languages (edge-tts voices)

| Language | Voice (female) | Voice (male) |
|----------|---------------|--------------|
| Japanese | ja-JP-NanamiNeural | ja-JP-KeitaNeural |
| Chinese (Mandarin) | zh-CN-XiaoxiaoNeural | zh-CN-YunxiNeural |
| Korean | ko-KR-SunHiNeural | ko-KR-InJoonNeural |
| English (US) | en-US-JennyNeural | en-US-GuyNeural |
| Spanish (ES) | es-ES-ElviraNeural | es-ES-AlvaroNeural |
| French | fr-FR-DeniseNeural | fr-FR-HenriNeural |
| German | de-DE-KatjaNeural | de-DE-ConradNeural |
| Portuguese | pt-BR-FranciscaNeural | pt-BR-AntonioNeural |

Run `edge-tts --list-voices` to see all 400+ available voices.
