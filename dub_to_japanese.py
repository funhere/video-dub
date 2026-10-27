#!/usr/bin/env python3
"""
dub_to_japanese.py — Download an IBM Media Center video and produce a
Japanese-dubbed version with business-style narration.

Pipeline:
  1. yt-dlp   → download original video (best mp4)
  2. ffmpeg   → extract audio track as WAV
  3. whisper  → transcribe English audio to text (with timestamps)
  4. Anthropic → translate transcript to Japanese business register (keigo)
  5. edge-tts → synthesize Japanese audio segments (ja-JP-NanamiNeural)
  6. ffmpeg   → merge segments, then replace original audio track

Usage:
  python3 scripts/dub_to_japanese.py \\
      "https://mediacenter.ibm.com/media/AI+Asset+Discovery/1_7o5msntb" \\
      --out ~/Downloads/

Requirements (all installable via pip / brew):
  yt-dlp, ffmpeg (system), openai-whisper, anthropic, edge-tts

Environment variables (read from .env in the project root):
  PM_ANTHROPIC_API_KEY   — Anthropic API key for translation
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Dependency check helpers
# ---------------------------------------------------------------------------

def _require(cmd: str) -> None:
    """Abort early if a system binary is missing."""
    if subprocess.run(["which", cmd], capture_output=True).returncode != 0:
        print(f"[ERROR] '{cmd}' not found on PATH. Install it first.", file=sys.stderr)
        sys.exit(1)


def _load_dotenv(project_root: Path) -> None:
    """Minimal .env loader — sets os.environ for keys not already set."""
    env_path = project_root / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


# ---------------------------------------------------------------------------
# Step 1 — Download video
# ---------------------------------------------------------------------------

def download_video(url: str, out_dir: Path) -> Path:
    """Download best mp4 stream via yt-dlp; return the local path."""
    print(f"\n[1/6] Downloading video from: {url}")
    out_dir.mkdir(parents=True, exist_ok=True)
    template = str(out_dir / "%(title)s.%(ext)s")
    result = subprocess.run(
        [
            "yt-dlp",
            "--no-playlist",
            "--format", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "--merge-output-format", "mp4",
            "--cookies-from-browser", "chrome",   # IBM Media Center requires SSO
            "--output", template,
            "--print", "after_move:filepath",      # print final path after download
            url,
        ],
        capture_output=False,
        text=True,
    )
    if result.returncode != 0:
        # Retry without browser cookies (public content)
        print("[1/6] Cookie-based download failed; retrying without --cookies-from-browser …")
        result = subprocess.run(
            [
                "yt-dlp",
                "--no-playlist",
                "--format", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                "--merge-output-format", "mp4",
                "--output", template,
                "--print", "after_move:filepath",
                url,
            ],
            capture_output=False,
            text=True,
        )
    if result.returncode != 0:
        print("[ERROR] yt-dlp download failed. See output above.", file=sys.stderr)
        sys.exit(1)

    # Find the downloaded mp4 (newest mp4 in out_dir)
    candidates = sorted(out_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        print("[ERROR] No .mp4 found after download.", file=sys.stderr)
        sys.exit(1)
    video_path = candidates[0]
    print(f"[1/6] Downloaded → {video_path}")
    return video_path


# ---------------------------------------------------------------------------
# Step 2 — Extract audio
# ---------------------------------------------------------------------------

def extract_audio(video_path: Path, work_dir: Path) -> Path:
    """Extract mono 16kHz WAV for whisper."""
    print("\n[2/6] Extracting audio …")
    wav_path = work_dir / "original_audio.wav"
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-ac", "1",            # mono
            "-ar", "16000",        # 16 kHz (whisper optimal)
            "-vn",                 # no video
            str(wav_path),
        ],
        check=True,
        capture_output=True,
    )
    print(f"[2/6] Audio extracted → {wav_path}")
    return wav_path


# ---------------------------------------------------------------------------
# Step 3 — Transcribe
# ---------------------------------------------------------------------------

def transcribe(wav_path: Path, work_dir: Path) -> list[dict]:
    """Run openai-whisper; return list of {start, end, text} segments."""
    print("\n[3/6] Transcribing with Whisper (this may take a few minutes) …")
    try:
        import whisper  # type: ignore
    except ImportError:
        print("[ERROR] openai-whisper not installed. Run: pip install openai-whisper", file=sys.stderr)
        sys.exit(1)

    model = whisper.load_model("base")
    result = model.transcribe(str(wav_path), language="en", task="transcribe",
                              verbose=False, word_timestamps=False)
    segments = [
        {"start": s["start"], "end": s["end"], "text": s["text"].strip()}
        for s in result["segments"]
        if s["text"].strip()
    ]
    transcript_path = work_dir / "transcript_en.json"
    transcript_path.write_text(
        json.dumps(segments, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[3/6] Transcribed {len(segments)} segments → {transcript_path}")
    return segments


# ---------------------------------------------------------------------------
# Step 4 — Translate to Japanese (business keigo)
# ---------------------------------------------------------------------------

TRANSLATE_SYSTEM = """\
You are a senior Japanese localization specialist for enterprise software product videos.
You receive an English transcript (JSON array of timed segments) and produce
a Japanese translation for voice dubbing.

Rules:
- Register: full keigo (です・ます調); customer-facing 丁寧語.
- Product / brand names kept in original (watsonx.governance, IBM, AI, API, etc.).
- Technical acronyms (AI, API, MLOps, LLM, SaaS) kept in original or first occurrence
  may use hybrid form 「日本語訳 (English)」— never repeated.
- Each segment must be translated independently; preserve the segment count and order.
- Keep the same JSON array structure: [{\"start\":…,\"end\":…,\"text\":\"日本語\"},…]
- Output ONLY valid JSON — no markdown fences, no explanation.
- CJK text calibration: Japanese speech runs ~7 mora/sec; if a segment's word count
  would be spoken much longer than (end-start) seconds, condense the meaning.
  Never exceed 1.5× the original duration.
"""


def translate_segments(segments: list[dict], work_dir: Path, api_key: str) -> list[dict]:
    """Translate segments to Japanese via Claude. Returns the translated segments."""
    print("\n[4/6] Translating to Japanese (business keigo) via Claude …")
    try:
        import anthropic  # type: ignore
    except ImportError:
        print("[ERROR] anthropic not installed. Run: pip install anthropic", file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    # Batch in chunks of 50 segments to stay within context limits
    translated: list[dict] = []
    chunk_size = 50
    for i in range(0, len(segments), chunk_size):
        chunk = segments[i:i + chunk_size]
        user_content = json.dumps(chunk, ensure_ascii=False, indent=2)
        message = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=4096,
            system=TRANSLATE_SYSTEM,
            messages=[{"role": "user", "content": user_content}],
        )
        raw = message.content[0].text.strip()
        # Strip accidental markdown fences
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        try:
            chunk_translated = json.loads(raw)
        except json.JSONDecodeError as exc:
            print(f"[WARN] JSON parse failed on chunk {i//chunk_size}: {exc}. "
                  "Falling back to original text for this chunk.", file=sys.stderr)
            chunk_translated = chunk
        translated.extend(chunk_translated)
        print(f"         … translated segments {i+1}-{min(i+chunk_size, len(segments))} "
              f"/ {len(segments)}")

    out_path = work_dir / "transcript_ja.json"
    out_path.write_text(json.dumps(translated, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[4/6] Translation complete → {out_path}")
    return translated


# ---------------------------------------------------------------------------
# Step 5 — Synthesize Japanese TTS
# ---------------------------------------------------------------------------

def synthesize_tts(segments: list[dict], work_dir: Path) -> list[Path]:
    """Use edge-tts to synthesize each segment; return list of mp3 paths."""
    print("\n[5/6] Synthesizing Japanese TTS (ja-JP-NanamiNeural) …")
    try:
        import edge_tts  # type: ignore  # noqa: F401
    except ImportError:
        print("[ERROR] edge-tts not installed. Run: pip install edge-tts", file=sys.stderr)
        sys.exit(1)

    import asyncio
    import edge_tts  # type: ignore

    audio_dir = work_dir / "tts_segments"
    audio_dir.mkdir(exist_ok=True)
    voice = "ja-JP-NanamiNeural"
    mp3_paths: list[Path] = []

    async def _synth_all() -> None:
        for idx, seg in enumerate(segments):
            out_path = audio_dir / f"seg_{idx:04d}.mp3"
            text = seg.get("text", "").strip()
            if not text:
                # Write 100ms silence placeholder
                subprocess.run(
                    ["ffmpeg", "-y", "-f", "lavfi", "-i",
                     f"anullsrc=r=24000:cl=mono,atrim=duration=0.1",
                     str(out_path)],
                    capture_output=True, check=False,
                )
                mp3_paths.append(out_path)
                continue
            communicate = edge_tts.Communicate(text=text, voice=voice, rate="+0%")
            await communicate.save(str(out_path))
            mp3_paths.append(out_path)
            if (idx + 1) % 10 == 0:
                print(f"         … {idx + 1}/{len(segments)} segments synthesized")

    asyncio.run(_synth_all())
    print(f"[5/6] TTS synthesis complete — {len(mp3_paths)} segments in {audio_dir}")
    return mp3_paths


# ---------------------------------------------------------------------------
# Step 6 — Build timed audio track + mux into video
# ---------------------------------------------------------------------------

def assemble_and_mux(
    segments: list[dict],
    mp3_paths: list[Path],
    video_path: Path,
    work_dir: Path,
    out_dir: Path,
) -> Path:
    """Pad/trim each TTS segment to its original timeslot, concat, mux into mp4."""
    print("\n[6/6] Assembling dubbed audio track and muxing …")

    # Get total video duration
    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_format", str(video_path)],
        capture_output=True, text=True, check=True,
    )
    total_duration = float(json.loads(probe.stdout)["format"]["duration"])

    # Build a list of timed audio pieces using ffmpeg complex filter
    # Strategy: for each segment, fit TTS into [start, end] window using atempo.
    # Segments are placed at their original start time; gaps become silence.
    parts_dir = work_dir / "tts_timed"
    parts_dir.mkdir(exist_ok=True)

    timed_parts: list[Path] = []
    prev_end = 0.0

    for idx, (seg, mp3) in enumerate(zip(segments, mp3_paths)):
        start = float(seg["start"])
        end = float(seg["end"])
        window = max(end - start, 0.1)

        # Silence gap before this segment
        gap = start - prev_end
        if gap > 0.01:
            sil = parts_dir / f"sil_{idx:04d}.wav"
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi",
                 "-i", f"anullsrc=r=24000:cl=mono,atrim=duration={gap:.4f}",
                 "-ar", "24000", "-ac", "1", str(sil)],
                capture_output=True, check=True,
            )
            timed_parts.append(sil)

        # Get TTS segment duration
        probe_seg = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", str(mp3)],
            capture_output=True, text=True,
        )
        if probe_seg.returncode != 0:
            tts_duration = window
        else:
            tts_duration = float(json.loads(probe_seg.stdout).get("format", {}).get("duration", window))

        # Fit TTS into the window via atempo (0.5 - 2.0 range)
        tempo = min(max(tts_duration / window, 0.5), 2.0)
        fitted = parts_dir / f"fit_{idx:04d}.wav"
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(mp3),
             "-af", f"atempo={tempo:.6f},apad=pad_dur={window:.4f},atrim=duration={window:.4f}",
             "-ar", "24000", "-ac", "1", str(fitted)],
            capture_output=True, check=True,
        )
        timed_parts.append(fitted)
        prev_end = end

    # Tail silence
    tail = total_duration - prev_end
    if tail > 0.01:
        sil_tail = parts_dir / "sil_tail.wav"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi",
             "-i", f"anullsrc=r=24000:cl=mono,atrim=duration={tail:.4f}",
             "-ar", "24000", "-ac", "1", str(sil_tail)],
            capture_output=True, check=True,
        )
        timed_parts.append(sil_tail)

    # Write concat list
    concat_list = parts_dir / "concat.txt"
    concat_list.write_text(
        "\n".join(f"file '{p.resolve()}'" for p in timed_parts),
        encoding="utf-8",
    )

    # Concatenate all parts into one dubbed audio track
    dubbed_audio = work_dir / "dubbed_audio.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
         "-i", str(concat_list), "-ar", "24000", "-ac", "1",
         str(dubbed_audio)],
        check=True, capture_output=True,
    )

    # Mux dubbed audio into the original video (replace audio stream)
    stem = video_path.stem
    out_path = out_dir / f"{stem}_japanese_dub.mp4"
    subprocess.run(
        ["ffmpeg", "-y",
         "-i", str(video_path),          # original video
         "-i", str(dubbed_audio),        # dubbed audio
         "-c:v", "copy",                 # copy video stream unchanged
         "-c:a", "aac", "-b:a", "192k",  # encode new audio
         "-map", "0:v:0",                # video from first input
         "-map", "1:a:0",                # audio from second input
         "-shortest",
         str(out_path)],
        check=True,
    )
    print(f"[6/6] Dubbed video → {out_path}")
    return out_path


# ---------------------------------------------------------------------------
# Main driver
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download an IBM Media Center video and produce a Japanese-dubbed version.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "url",
        nargs="?",
        default="https://mediacenter.ibm.com/media/AI+Asset+Discovery/1_7o5msntb",
        help="Video URL (default: AI Asset Discovery demo)",
    )
    parser.add_argument(
        "--out", "-o",
        default=str(Path.home() / "Downloads"),
        help="Output directory (default: ~/Downloads)",
    )
    parser.add_argument(
        "--work-dir",
        help="Scratch directory for intermediates (default: auto tempdir)",
    )
    parser.add_argument(
        "--skip-download",
        metavar="VIDEO_PATH",
        help="Skip yt-dlp; use this local video file instead",
    )
    args = parser.parse_args()

    # Load .env from project root (two levels up from scripts/)
    project_root = Path(__file__).resolve().parent.parent
    _load_dotenv(project_root)

    api_key = os.environ.get("PM_ANTHROPIC_API_KEY", "")
    if not api_key:
        print("[ERROR] PM_ANTHROPIC_API_KEY not set. "
              "Add it to .env or set the environment variable.", file=sys.stderr)
        sys.exit(1)

    _require("ffmpeg")
    _require("ffprobe")

    out_dir = Path(args.out).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    use_tempdir = args.work_dir is None
    work_dir_ctx = (
        tempfile.TemporaryDirectory(prefix="ppt-master-dub-")
        if use_tempdir
        else None
    )
    work_dir = (
        Path(work_dir_ctx.name) if work_dir_ctx
        else Path(args.work_dir).expanduser().resolve()
    )
    work_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Step 1
        if args.skip_download:
            video_path = Path(args.skip_download).expanduser().resolve()
            print(f"[1/6] Skipping download; using {video_path}")
        else:
            _require("yt-dlp")
            video_path = download_video(args.url, out_dir)

        # Step 2
        wav_path = extract_audio(video_path, work_dir)

        # Step 3
        segments = transcribe(wav_path, work_dir)

        # Step 4
        ja_segments = translate_segments(segments, work_dir, api_key)

        # Step 5
        mp3_paths = synthesize_tts(ja_segments, work_dir)

        # Step 6
        dubbed_path = assemble_and_mux(ja_segments, mp3_paths, video_path, work_dir, out_dir)

        print(f"\n✅ Done! Japanese-dubbed video saved to:\n   {dubbed_path}")
        print(f"\n   Intermediate files in: {work_dir}")
        print("   (Delete the work dir when no longer needed.)")

    finally:
        # Keep tempdir if the user passed --work-dir (they own it)
        if work_dir_ctx is not None:
            print(f"\n[NOTE] Scratch files kept at: {work_dir_ctx.name}")
            print("       Pass --work-dir <path> to control the location.")
            # Don't auto-cleanup so the user can inspect intermediates
            work_dir_ctx.cleanup = lambda: None  # suppress auto-delete


if __name__ == "__main__":
    main()
