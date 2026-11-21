---
name: video-dub
description: >
  Dub an MP4 video into another language. Transcribes with faster-whisper,
  translates via the calling agent's built-in LLM, synthesizes with edge-tts,
  aligns audio to video frames (freeze-frame fallback), and burns in subtitles.
  Supports two pipeline modes: (A) whisper-segment mode (fast, good for most
  content) and (B) sentence-fluency mode (best for long-form speech with
  sentence-complete phrasing and steady pace). No external API key required.
---


# video-dub Skill

Dub any MP4 video into another language. Translation is performed by the
**calling agent's own LLM** (Claude Code, Codex, WorkBuddy, Doubao, etc.) —
no additional API key is needed.

---

## Overview

```
Source MP4
   │
   ▼
[Step 1] faster-whisper ──→ transcript_en.json  (per-segment timestamps)
   │
   ▼
[Step 2] Agent LLM ────────→ transcript_<lang>.json  (translated, same timestamps)
   │
   ▼ ← (Mode B only: split_sentences → merge_chunks → post_merge)
   │
[Step 3] edge-tts ─────────→ tts_segments/seg_NNNN.mp3
   │
   ▼
[Step 4] assemble.py ──────→ assembled/video_joined.mp4
                              assembled/audio_joined.wav
                              assembled/subtitles.srt
   │
   ▼
[Step 5] mux.py ───────────→ output_<lang>.mp4  (video + dubbed audio + subtitles)
```

**Two pipeline modes:**

| Mode | Use when | Segments | Quality |
|------|----------|----------|---------|
| **A — Whisper-segment** | Speed, demos, any content | Each whisper segment = one TTS unit | Fast; may cut mid-sentence |
| **B — Sentence-fluency** | Long-form narration, natural pacing | Sentences merged into window-fitting chunks | Smooth; never breaks mid-sentence |

---

## Prerequisites

**System (must be on PATH):**
- `ffmpeg` ≥ 5.0 with libx264
- `ffprobe` (bundled with ffmpeg)
- Python ≥ 3.10

**Python (run `install.sh` once):**
- `faster-whisper`
- `edge-tts`

**API keys:** none.

```bash
cd scripts/video_dub
bash install.sh
```

---

## Quick Start

### Mode A — Whisper-segment (fast)

```bash
# Phase 1: transcribe (runs Step 1, then prints translation task)
python3 pipeline.py \
  --video  /path/to/source.mp4 \
  --lang   zh \
  --voice  zh-CN-YunjianNeural \
  --rate   "+15%"

# Phase 2: resume after agent writes translated JSON
python3 pipeline.py \
  --video      /path/to/source.mp4 \
  --translated /path/to/source_dub_work/transcript_zh.json \
  --voice      zh-CN-YunjianNeural \
  --out        /path/to/source_zh.mp4
```

### Mode B — Sentence-fluency (recommended for long-form speech)

```bash
WORK="/path/to/source_dub_work"
VIDEO="/path/to/source.mp4"
LANG="zh"
VOICE="zh-CN-YunjianNeural"
RATE="+15%"

# B-1  Transcribe
python3 steps/transcribe.py --video "$VIDEO" --out "$WORK/transcript_en.json"

# B-2  Split at sentence boundaries → sentences_en.json
python3 steps/split_sentences.py --transcript "$WORK/transcript_en.json" \
  --out "$WORK/sentences_en.json"

# B-3  Agent: translate sentences (see "Agent translation task" below)
#      → agent writes $WORK/transcript_zh_sent.json

# B-4  Greedy chunk merge: grow until chunk fits its window at RATE cps
python3 steps/merge_chunks.py \
  --sentences-en "$WORK/sentences_en.json" \
  --sentences-zh "$WORK/transcript_zh_sent.json" \
  --total-dur    1253.1 \
  --rate         4.9 \
  --out          "$WORK/transcript_zh_chunks.json"

# B-5  TTS synthesis (preliminary, to measure actual durations)
python3 steps/synthesize.py \
  --transcript "$WORK/transcript_zh_chunks.json" \
  --voice      "$VOICE" \
  --rate       "$RATE" \
  --out-dir    "$WORK/tts_chunks"

# B-6  Post-merge: re-merge any chunk whose real TTS overruns its window
python3 steps/post_merge.py \
  --chunks   "$WORK/transcript_zh_chunks.json" \
  --tts-dir  "$WORK/tts_chunks" \
  --total-dur 1253.1 \
  --out      "$WORK/transcript_zh_chunks_v2.json"

# B-7  Re-synthesize final chunks (skips unchanged files)
python3 steps/synthesize.py \
  --transcript "$WORK/transcript_zh_chunks_v2.json" \
  --voice      "$VOICE" \
  --rate       "$RATE" \
  --out-dir    "$WORK/tts_chunks_v2"

# B-8  Assemble: stitch video + audio segments, build SRT
python3 steps/assemble.py \
  --video      "$VIDEO" \
  --transcript "$WORK/transcript_zh_chunks_v2.json" \
  --tts-dir    "$WORK/tts_chunks_v2" \
  --out-dir    "$WORK/assembled_v2" \
  --crf        22

# B-9  Mux: merge video + audio + burned-in subtitles
python3 steps/mux.py \
  --video   "$WORK/assembled_v2/video_joined.mp4" \
  --audio   "$WORK/assembled_v2/audio_joined.wav" \
  --srt     "$WORK/assembled_v2/subtitles.srt" \
  --out     "/path/to/source_zh_v2.mp4" \
  --lang    zh \
  --title   "中文" \
  --subtitle-mode both \
  --font-size 32 \
  --wrap-chars 25 \
  --crf     20
```

---

## Directory Layout

```
video_dub/
├── SKILL.md              ← this file (AI agent entry point)
├── README.md             ← human setup guide
├── requirements.txt
├── install.sh
├── pipeline.py           ← all-in-one runner (Mode A)
└── steps/
    ├── transcribe.py     ← Step 1: faster-whisper → transcript_en.json
    ├── translate.py      ← Step 2: print translation task / parse agent output
    ├── split_sentences.py← (Mode B) re-segment at sentence boundaries
    ├── merge_chunks.py   ← (Mode B) greedy window-fit merger
    ├── post_merge.py     ← (Mode B) actual-TTS-duration second pass
    ├── synthesize.py     ← Step 3: edge-tts → seg_NNNN.mp3
    ├── assemble.py       ← Step 4: per-segment video+audio concat → SRT
    └── mux.py            ← Step 5: burn subtitles + mux audio → final MP4
```

Work artifacts live in `<video_stem>_dub_work/` next to the source file.

---

## Agent Translation Task (Step 2 / B-3)

### Mode A — translate whisper segments

The agent receives `transcript_en.json` (array of `{start, end, text}`) and
must write `transcript_<lang>.json` with **exactly the same number of objects**,
same `start`/`end` values, only `text` replaced.

Constraints:
- Preserve proper nouns, brand names, technical terms verbatim
- Each translated segment must fit in roughly `1.3 × (end − start)` seconds at
  natural speech rate for the target language
- One output object per input object — do **not** merge or split

### Mode B — translate sentences

The agent receives `sentences_en.json` (array of English sentences) and must
write `transcript_<lang>_sent.json` with the **same array length**, same
`{start, end}` timestamps, only `text` replaced with the full translated sentence.

Constraints:
- Translate as complete sentences — never truncate
- Preserve sentence boundaries (1 input → 1 output)
- After translation the merge_chunks step handles fitting to windows; the agent
  does **not** need to worry about timing budgets

---

## Core Algorithms

### Sentence boundary splitter (`split_sentences.py`)

Builds a monotonic `(char_position → time)` map from all whisper segments via
linear interpolation within each segment. Splits the concatenated transcript at
`. ! ?` while skipping:
- Abbreviations: `U.S.`, `Mr.`, `Dr.`, `Gen.`, `Col.`, `Lt.` etc.
- Decimal numbers: `1.76`, `8.2`
- Single-uppercase initials (e.g., the `S` in `U.S.A.`)

Result: N sentences each with interpolated `{start, end, text}`.

### Shortest-greedy chunk merger (`merge_chunks.py`)

```
RATE = effective_cps × safety_factor   # e.g. 4.9 for YunjianNeural +15%

i = 0
while i < N:
    chunk_start = sentences[i].start
    chunk_text  = sentences[i].text

    while True:
        window = sentences[j+1].start − chunk_start   (or video_end if last)
        if len(chunk_text) / RATE <= window:
            break          # fits — emit chunk [i..j]
        j += 1
        chunk_text += sentences[j].text   # absorb next sentence

    emit chunk; i = j + 1
```

No sentence is ever split. The merge always tries to emit the fewest sentences
that fit the available window.

### Post-merge with real TTS durations (`post_merge.py`)

After the preliminary TTS synthesis, measure each chunk's actual MP3 duration
via `ffprobe`. Any chunk where `tts_dur > window + 0.04s` (FREEZE_THRESHOLD) is
merged into the next chunk. Repeat until no overruns remain (converges in ≤3
iterations for well-budgeted content).

This corrects for per-chunk TTS overhead (preamble silence, breath pause,
edge-tts warm-up) which cannot be predicted from character counts alone.

### Freeze-frame assembly (`assemble.py`)

```
for each chunk i:
    window  = chunks[i+1].start − chunks[i].start   (or video_end)
    tts_dur = duration of seg_i.mp3

    video_clip = original[chunks[i].start : chunks[i].start + window]
    if tts_dur > window:                     # should be 0 after post_merge
        video_clip += freeze_last_frame(tts_dur − window)
    audio_clip = seg_i.mp3
    if tts_dur < window:
        audio_clip += silence(window − tts_dur)
```

Total output duration ≈ original duration ± rounding error (<1s).

### Subtitle auto-wrap (`mux.py`)

Before writing each subtitle cue to a drawtext textfile, `_wrap_text()` splits
at CJK punctuation marks (`，。！？；：`) and hard-wraps at `--wrap-chars`
CJK units (CJK char = 1 unit, ASCII char = 0.5 unit). This keeps long merged
subtitles readable without overflowing the frame.

```
--wrap-chars 25   # ≈ 800px per line at font_size=32 on 1920px video
```

---

## Rate Calibration

For each voice+rate combination, measure effective chars-per-second (cps):

```bash
# Synthesize a 30–50 char test sentence, measure duration
echo '{"text": "这是一段用于测量语速的中文测试语句"}' | \
  python3 -c "
import asyncio, edge_tts, subprocess, json, sys
t = json.load(sys.stdin)['text']
async def go():
    c = edge_tts.Communicate(t, 'zh-CN-YunjianNeural', rate='+15%')
    await c.save('/tmp/rate_test.mp3')
asyncio.run(go())
r = subprocess.run(['ffprobe','-v','quiet','-show_entries','format=duration',
  '-of','csv=p=0','/tmp/rate_test.mp3'], capture_output=True, text=True)
dur = float(r.stdout.strip())
print(f'{len(t)} chars / {dur:.3f}s = {len(t)/dur:.2f} cps')
"
```

Recommended planning rates (measured + ~8% safety margin):

| Voice | Rate flag | Measured cps | Planning RATE |
|-------|-----------|-------------|---------------|
| zh-CN-YunjianNeural | +15% | ~5.30 | 4.9 |
| zh-CN-XiaoxiaoNeural | +10% | ~4.80 | 4.5 |
| ja-JP-KeitaNeural | +15% | ~8.50 mora/s | 7.8 |
| en-US-GuyNeural | +10% | ~14.0 | 13.0 |

---

## Key Parameters

### pipeline.py / synthesize.py / assemble.py / mux.py

| Flag | Default | Description |
|------|---------|-------------|
| `--lang` | `ja` | BCP-47 target language (`zh`, `ko`, `en`, `de`, …) |
| `--voice` | `ja-JP-NanamiNeural` | Any `edge-tts` voice name |
| `--rate` | `+15%` | Speech rate offset: `+10%`, `+15%`, `+20%` |
| `--whisper-model` | `medium` | `tiny` / `base` / `small` / `medium` / `large-v3` |
| `--crf` | `22` | x264 CRF for re-encoded video (18=high quality, 28=small file) |
| `--subtitle-mode` | `hard` | `hard` = burned-in; `soft` = mov_text; `both` = both |
| `--font-size` | `28` | Subtitle font size in pixels |
| `--wrap-chars` | `0` | Max CJK units per subtitle line (0 = disabled) |
| `--total-dur` | — | (Mode B) video duration in seconds, used for last-window calc |

### merge_chunks.py

| Flag | Default | Description |
|------|---------|-------------|
| `--rate` | `4.9` | Planning cps rate for the target language/voice |
| `--total-dur` | — | Video duration (seconds) |

---

## Supported Voices

Run `edge-tts --list-voices` for all 400+ voices.

| Language | Female | Male (沉稳/composed) |
|----------|--------|---------------------|
| Chinese (Mandarin) | zh-CN-XiaoxiaoNeural | **zh-CN-YunjianNeural** ← recommended |
| Chinese (Mandarin) | zh-CN-XiaoyiNeural | zh-CN-YunxiNeural |
| Japanese | ja-JP-NanamiNeural | ja-JP-KeitaNeural |
| Korean | ko-KR-SunHiNeural | ko-KR-InJoonNeural |
| English (US) | en-US-JennyNeural | en-US-GuyNeural |
| English (UK) | en-GB-SoniaNeural | en-GB-RyanNeural |
| Spanish | es-ES-ElviraNeural | es-ES-AlvaroNeural |
| French | fr-FR-DeniseNeural | fr-FR-HenriNeural |
| German | de-DE-KatjaNeural | de-DE-ConradNeural |
| Portuguese | pt-BR-FranciscaNeural | pt-BR-AntonioNeural |
| Arabic | ar-SA-ZariyahNeural | ar-SA-HamedNeural |

---

## LLM Workflow Instructions

> Read this section when invoked as an AI coding agent (Claude Code, Codex,
> WorkBuddy, Doubao, IBM Bob, etc.)

### Decision: Mode A or Mode B?

```
Is the content long-form narration (documentary, lecture, explainer)?
  AND does the user want natural sentence-complete phrasing?
  AND is the target language syllable-dense relative to the source (e.g. EN→ZH)?
  → Use Mode B (sentence-fluency pipeline)

Otherwise (short clips, demos, segment-by-segment is fine):
  → Use Mode A (whisper-segment pipeline)
```

### Mode A — step-by-step agent workflow

1. Read this SKILL.md
2. Confirm: source video path, target language, desired voice, gender preference
3. Run `install.sh` once (check for `.venv/` to skip if already done)
4. Run `steps/transcribe.py` → `transcript_en.json`
5. Read `transcript_en.json`; translate all segments; write `transcript_<lang>.json`
   - Same array length, same start/end, only text changed
   - Budget check: `len(translated_text) / RATE < (end − start) × 1.3`
6. Run `steps/synthesize.py`
7. Run `steps/assemble.py`
8. Run `steps/mux.py` with `--subtitle-mode both --wrap-chars 25`
9. Report output path, duration, file size

### Mode B — step-by-step agent workflow

1. Read this SKILL.md
2. Confirm: source video path, target language, voice, rate, planning RATE
3. Run `install.sh` once if needed
4. **B-1** `steps/transcribe.py` → `transcript_en.json`
5. **B-2** `steps/split_sentences.py` → `sentences_en.json`
   - Print the sentence count and first few sentences to verify segmentation
6. **B-3** Read `sentences_en.json`; translate each sentence; write `transcript_<lang>_sent.json`
   - Same array length, same start/end, full sentence translation
   - Do NOT truncate; the merge step handles timing
7. **B-4** `steps/merge_chunks.py` → `transcript_<lang>_chunks.json`
   - Print the audit output; note any OVER-budget chunks (expected: 0 or few)
8. **B-5** `steps/synthesize.py` on `transcript_<lang>_chunks.json` → `tts_chunks/`
9. **B-6** `steps/post_merge.py` → `transcript_<lang>_chunks_v2.json`
   - Print merge count; if >10 merges, consider raising `--rate` and re-running B-4
10. **B-7** `steps/synthesize.py` on `chunks_v2.json` → `tts_chunks_v2/`
    - Verify: `missing=0 overruns>40ms=0`
11. **B-8** `steps/assemble.py` → `assembled_v2/`
    - Verify: `freeze-extended: 0 segs`
12. **B-9** `steps/mux.py` with `--wrap-chars 25 --subtitle-mode both`
13. Report output path, duration (should be within ±1s of original), file size

### Common troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `freeze-extended: N segs` after assemble | TTS overruns survived post_merge | Increase `--rate` in merge_chunks, re-run from B-4 |
| Many chunks merged in post_merge (>15) | Planning RATE too optimistic | Measure real cps; set RATE = measured × 0.92 |
| Subtitles off-screen (too wide) | Long merged chunk, no wrap | Add `--wrap-chars 25` to mux |
| edge-tts connection error | Network blip | Re-run synthesize.py; it skips existing non-empty files |
| Translation count mismatch | Agent split/merged items | Re-translate; verify `len(output) == len(input)` |
| Output duration >> original | Many freeze-frame extensions | Lower RATE, re-run from B-4; or use Mode A |

---

## End-to-End Example (Chinese male voice, documentary)

```bash
VIDEO="/path/to/documentary.mp4"
WORK="${VIDEO%.*}_dub_work"
LANG="zh"
VOICE="zh-CN-YunjianNeural"
RATE="+15%"
RATE_CPS=4.9

mkdir -p "$WORK"

# B-1 Transcribe
python3 steps/transcribe.py \
  --video "$VIDEO" --out "$WORK/transcript_en.json" --model medium

# B-2 Split sentences
python3 steps/split_sentences.py \
  --transcript "$WORK/transcript_en.json" \
  --out "$WORK/sentences_en.json"

# B-3 Agent translates → $WORK/transcript_zh_sent.json

# B-4 Greedy merge
TOTAL=$(ffprobe -v quiet -show_entries format=duration \
  -of csv=p=0 "$VIDEO")
python3 steps/merge_chunks.py \
  --sentences-en "$WORK/sentences_en.json" \
  --sentences-zh "$WORK/transcript_zh_sent.json" \
  --total-dur    "$TOTAL" \
  --rate         "$RATE_CPS" \
  --out          "$WORK/transcript_zh_chunks.json"

# B-5 Preliminary TTS
python3 steps/synthesize.py \
  --transcript "$WORK/transcript_zh_chunks.json" \
  --voice "$VOICE" --rate "$RATE" --out-dir "$WORK/tts_chunks"

# B-6 Post-merge
python3 steps/post_merge.py \
  --chunks   "$WORK/transcript_zh_chunks.json" \
  --tts-dir  "$WORK/tts_chunks" \
  --total-dur "$TOTAL" \
  --out      "$WORK/transcript_zh_chunks_v2.json"

# B-7 Final TTS
python3 steps/synthesize.py \
  --transcript "$WORK/transcript_zh_chunks_v2.json" \
  --voice "$VOICE" --rate "$RATE" --out-dir "$WORK/tts_chunks_v2"

# B-8 Assemble
python3 steps/assemble.py \
  --video      "$VIDEO" \
  --transcript "$WORK/transcript_zh_chunks_v2.json" \
  --tts-dir    "$WORK/tts_chunks_v2" \
  --out-dir    "$WORK/assembled_v2" --crf 22

# B-9 Mux
python3 steps/mux.py \
  --video   "$WORK/assembled_v2/video_joined.mp4" \
  --audio   "$WORK/assembled_v2/audio_joined.wav" \
  --srt     "$WORK/assembled_v2/subtitles.srt" \
  --out     "${VIDEO%.*}_zh.mp4" \
  --lang    zh --title "中文" \
  --subtitle-mode both --font-size 32 --wrap-chars 25 --crf 20
```

---

## Quality Checklist (agent self-verification)

After each run, verify:

- [ ] `freeze-extended: 0 segs` in assemble output
- [ ] `overruns>40ms=0` in synthesize audit
- [ ] Output duration within ±1s of original
- [ ] No chunk missing (`missing=0`)
- [ ] Subtitles visible and readable (check a sample frame)
- [ ] Final file size reasonable (170–250 MB per 20-minute 1080p video)
