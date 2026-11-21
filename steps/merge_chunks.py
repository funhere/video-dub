#!/usr/bin/env python3
"""
Step B-4 — Shortest-greedy chunk merger.

Reads parallel sentence arrays (source language for timestamps, target
language for text) and merges them into the minimum number of chunks
such that each chunk's text fits in its video window at the given planning
chars-per-second rate.

No sentence is ever split across chunks.

Output: JSON array of {start, end, text} — the translated chunks.
"""
import argparse
import json
import sys
from pathlib import Path


def merge_chunks(
    en_sents: list[dict],
    zh_sents: list[dict],
    total_dur: float,
    rate: float,
) -> list[dict]:
    assert len(en_sents) == len(zh_sents), (
        f"Sentence count mismatch: en={len(en_sents)} zh={len(zh_sents)}"
    )
    # Merge source timestamps with target text
    sents = [
        {"start": e["start"], "end": e["end"], "text": z["text"]}
        for e, z in zip(en_sents, zh_sents)
    ]

    N = len(sents)
    chunks: list[dict] = []
    i = 0
    while i < N:
        chunk_start = sents[i]["start"]
        texts = [sents[i]["text"]]
        chars = len(sents[i]["text"])
        j = i
        while True:
            next_start = sents[j + 1]["start"] if j + 1 < N else total_dur
            window = next_start - chunk_start
            if chars / rate <= window:
                break
            if j + 1 >= N:
                break
            j += 1
            texts.append(sents[j]["text"])
            chars += len(sents[j]["text"])
        chunks.append({
            "start": chunk_start,
            "end": sents[j]["end"],
            "text": "".join(texts),
        })
        i = j + 1
    return chunks


def audit(chunks: list[dict], total_dur: float, rate: float) -> int:
    over = 0
    for i, c in enumerate(chunks):
        next_start = chunks[i + 1]["start"] if i + 1 < len(chunks) else total_dur
        window = next_start - c["start"]
        needed = len(c["text"]) / rate
        slack = window - needed
        flag = "OVER" if slack < 0 else "OK  "
        if slack < 0:
            over += 1
        print(
            f"  [{i:3d}] {c['start']:7.2f}s  w={window:6.2f}s  "
            f"chars={len(c['text']):3d}  needed={needed:5.2f}s  "
            f"slack={slack:+5.2f}s  {flag}  {c['text'][:70]}"
        )
    return over


def main() -> None:
    p = argparse.ArgumentParser(
        description="Greedy chunk merger: grow until chunk fits video window"
    )
    p.add_argument("--sentences-en", required=True, type=Path,
                   help="sentences_en.json (source, for timestamps)")
    p.add_argument("--sentences-zh", required=True, type=Path,
                   help="transcript_<lang>_sent.json (target, for text)")
    p.add_argument("--total-dur", required=True, type=float,
                   help="Video duration in seconds (from ffprobe)")
    p.add_argument("--rate", type=float, default=4.9,
                   help="Planning chars-per-second for TTS voice (default 4.9)")
    p.add_argument("--out", required=True, type=Path,
                   help="Output path for merged chunks JSON")
    args = p.parse_args()

    for path, flag in [(args.sentences_en, "--sentences-en"),
                       (args.sentences_zh, "--sentences-zh")]:
        if not path.exists():
            sys.exit(f"ERROR: {flag} not found: {path}")

    en_sents = json.loads(args.sentences_en.read_text(encoding="utf-8"))
    zh_sents = json.loads(args.sentences_zh.read_text(encoding="utf-8"))

    chunks = merge_chunks(en_sents, zh_sents, args.total_dur, args.rate)

    print(f"[merge_chunks] {len(en_sents)} sentences → {len(chunks)} chunks  "
          f"(rate={args.rate} cps, total={args.total_dur:.1f}s)")
    over = audit(chunks, args.total_dur, args.rate)
    print(f"\n[merge_chunks] OVER-budget chunks: {over}  "
          f"(will be fixed by post_merge.py after real TTS synthesis)")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    out_data = [{"start": c["start"], "end": c["end"], "text": c["text"]}
                for c in chunks]
    args.out.write_text(
        json.dumps(out_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[merge_chunks] wrote {args.out}")


if __name__ == "__main__":
    main()
