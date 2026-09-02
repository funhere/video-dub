#!/usr/bin/env python3
"""
Step 1 — Transcribe source video to timestamped JSON segments.

Output format:
  [{"start": 0.0, "end": 7.0, "text": "..."}, ...]
"""
import argparse
import json
import sys
from pathlib import Path


def transcribe(video: Path, model_size: str, language: str | None) -> list[dict]:
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        sys.exit("ERROR: faster-whisper not installed. Run install.sh first.")

    print(f"[transcribe] Loading Whisper model '{model_size}'...")
    model = WhisperModel(model_size, device="cpu", compute_type="int8")

    print(f"[transcribe] Transcribing {video.name} ...")
    kwargs: dict = dict(
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
    )
    if language:
        kwargs["language"] = language

    segments, info = model.transcribe(str(video), **kwargs)
    print(f"[transcribe] Detected language: {info.language} ({info.language_probability:.1%})")

    result = []
    for seg in segments:
        result.append({"start": round(seg.start, 3), "end": round(seg.end, 3), "text": seg.text.strip()})
        print(f"  [{seg.start:6.1f}s → {seg.end:6.1f}s] {seg.text.strip()[:80]}")

    return result


def main() -> None:
    p = argparse.ArgumentParser(description="Transcribe video with faster-whisper")
    p.add_argument("--video",         required=True, type=Path)
    p.add_argument("--out",           required=True, type=Path, help="Output JSON path")
    p.add_argument("--model",         default="medium",
                   choices=["tiny", "base", "small", "medium", "large-v2", "large-v3"])
    p.add_argument("--language",      default=None,  help="Force source language (e.g. en)")
    args = p.parse_args()

    if not args.video.exists():
        sys.exit(f"ERROR: video not found: {args.video}")

    segs = transcribe(args.video, args.model, args.language)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(segs, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[transcribe] {len(segs)} segments → {args.out}")


if __name__ == "__main__":
    main()
