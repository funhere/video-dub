#!/usr/bin/env python3
"""
Step 3 — Synthesize TTS audio for each segment using edge-tts.

Produces: {out_dir}/seg_0000.mp3 … seg_NNNN.mp3
"""
import argparse
import asyncio
import json
import subprocess
import sys
from pathlib import Path


async def _synth_all(segs: list[dict], voice: str, rate: str, out_dir: Path) -> list[Path]:
    try:
        import edge_tts
    except ImportError:
        sys.exit("ERROR: edge-tts not installed. Run install.sh first.")

    paths: list[Path] = []
    for idx, seg in enumerate(segs):
        out = out_dir / f"seg_{idx:04d}.mp3"
        text = (seg.get("text") or "").strip()
        if out.exists():
            paths.append(out)
            continue
        if text:
            comm = edge_tts.Communicate(text=text, voice=voice, rate=rate)
            await comm.save(str(out))
        else:
            # Empty segment — generate minimal silence placeholder
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi", "-i",
                 "anullsrc=r=24000:cl=mono,atrim=duration=0.1", str(out)],
                capture_output=True, check=True,
            )
        paths.append(out)
        if (idx + 1) % 10 == 0 or idx + 1 == len(segs):
            print(f"  [synthesize] {idx + 1}/{len(segs)} segments")

    return paths


def main() -> None:
    p = argparse.ArgumentParser(description="Synthesize TTS with edge-tts")
    p.add_argument("--transcript", required=True, type=Path, help="Translated JSON")
    p.add_argument("--out-dir",    required=True, type=Path, help="Directory for MP3 output")
    p.add_argument("--voice",      default="ja-JP-NanamiNeural",
                   help="edge-tts voice name (run 'edge-tts --list-voices' to browse)")
    p.add_argument("--rate",       default="+15%",
                   help="Speech rate offset, e.g. +15%% or -10%%")
    args = p.parse_args()

    if not args.transcript.exists():
        sys.exit(f"ERROR: transcript not found: {args.transcript}")

    segs = json.loads(args.transcript.read_text(encoding="utf-8"))
    args.out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[synthesize] {len(segs)} segments, voice={args.voice}, rate={args.rate}")
    paths = asyncio.run(_synth_all(segs, args.voice, args.rate, args.out_dir))
    print(f"[synthesize] done — {len(paths)} MP3 files in {args.out_dir}")


if __name__ == "__main__":
    main()
