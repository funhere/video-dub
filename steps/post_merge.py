#!/usr/bin/env python3
"""
Step B-6 — Post-merge using actual TTS durations.

After the preliminary TTS synthesis, measure each chunk's real MP3 duration
via ffprobe. Any chunk whose tts_dur > window + FREEZE_THRESHOLD is merged
forward into the next chunk (absorbing one more sentence). Repeat until no
overruns remain (converges in ≤ 3 iterations for well-budgeted content).

This corrects for per-chunk TTS overhead (preamble silence, breath pause,
edge-tts warm-up jitter) which cannot be predicted from character counts.

Output: JSON array of {start, end, text} — final merged chunks.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path


FREEZE_THRESHOLD = 0.04  # seconds: overruns below this absorbed as silence


def probe_duration(path: Path) -> float:
    if not path.exists():
        return 0.0
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    return float(r.stdout.strip() or "0")


def post_merge(
    chunks: list[dict],
    tts_dir: Path,
    total_dur: float,
    freeze_threshold: float = FREEZE_THRESHOLD,
) -> tuple[list[dict], int]:
    rows = []
    for i, c in enumerate(chunks):
        tts = probe_duration(tts_dir / f"seg_{i:04d}.mp3")
        rows.append({
            "start": c["start"],
            "end": c["end"],
            "text": c["text"],
            "tts": tts,
        })

    total_merges = 0
    iters = 0
    changed = True
    while changed and iters < 20:
        changed = False
        iters += 1
        i = 0
        while i < len(rows):
            next_start = rows[i + 1]["start"] if i + 1 < len(rows) else total_dur
            window = next_start - rows[i]["start"]
            if rows[i]["tts"] > window + freeze_threshold and i + 1 < len(rows):
                # Merge i and i+1; estimate new TTS as sum minus one overhead
                merged = {
                    "start": rows[i]["start"],
                    "end":   rows[i + 1]["end"],
                    "text":  rows[i]["text"] + rows[i + 1]["text"],
                    "tts":   rows[i]["tts"] + rows[i + 1]["tts"] - 0.4,
                }
                rows[i] = merged
                del rows[i + 1]
                total_merges += 1
                changed = True
                continue
            i += 1

    return rows, total_merges


def main() -> None:
    p = argparse.ArgumentParser(
        description="Second-pass merger using real TTS durations from ffprobe"
    )
    p.add_argument("--chunks", required=True, type=Path,
                   help="transcript_<lang>_chunks.json from merge_chunks.py")
    p.add_argument("--tts-dir", required=True, type=Path,
                   help="Directory with seg_NNNN.mp3 from preliminary synthesis")
    p.add_argument("--total-dur", required=True, type=float,
                   help="Video duration in seconds")
    p.add_argument("--freeze-threshold", type=float, default=FREEZE_THRESHOLD,
                   help=f"Overrun tolerance in seconds (default {FREEZE_THRESHOLD})")
    p.add_argument("--out", required=True, type=Path,
                   help="Output path for final chunks JSON")
    args = p.parse_args()

    for path, flag in [(args.chunks, "--chunks"), (args.tts_dir, "--tts-dir")]:
        if not path.exists():
            sys.exit(f"ERROR: {flag} not found: {path}")

    chunks = json.loads(args.chunks.read_text(encoding="utf-8"))
    rows, total_merges = post_merge(
        chunks, args.tts_dir, args.total_dur, args.freeze_threshold
    )

    print(f"[post_merge] {len(chunks)} chunks → {len(rows)} chunks  "
          f"({total_merges} merges)")

    # Final overrun audit
    over = 0
    for i, r in enumerate(rows):
        next_start = rows[i + 1]["start"] if i + 1 < len(rows) else args.total_dur
        window = next_start - r["start"]
        tts = probe_duration(args.tts_dir / f"seg_{i:04d}.mp3")
        overrun = tts - window
        if overrun > args.freeze_threshold:
            over += 1
            print(f"  STILL OVER chunk {i}: window={window:.2f}s tts={tts:.2f}s "
                  f"overrun={overrun:.3f}s :: {r['text'][:60]}")
    print(f"[post_merge] remaining overruns>{args.freeze_threshold}s: {over}")
    if over > 0:
        print("  → Re-synthesize and re-run post_merge, or raise --rate in merge_chunks")

    out_data = [{"start": r["start"], "end": r["end"], "text": r["text"]}
                for r in rows]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(out_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[post_merge] wrote {args.out}")


if __name__ == "__main__":
    main()
