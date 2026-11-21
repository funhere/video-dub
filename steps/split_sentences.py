#!/usr/bin/env python3
"""
Step B-2 — Split whisper segments into sentence-level chunks.

Builds a monotonic char→time map from all whisper segments via linear
interpolation, then splits the concatenated transcript at sentence
boundaries (. ! ?) while skipping abbreviations and decimal numbers.

Output: JSON array of {start, end, text} at sentence granularity.
"""
import argparse
import json
import re
import sys
from pathlib import Path


# Abbreviations that end with "." but are NOT sentence endings.
_ABBREV_RE = re.compile(
    r"\b(U\.S|U\.K|U\.N|e\.g|i\.e|Mr|Mrs|Dr|Ms|Prof|Gen|Maj|Sgt|Lt|Col|"
    r"St|No|Inc|Co|Ltd|Jr|Sr|Mt|vs|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)$"
)


def build_breakpoints(segs: list[dict]) -> list[tuple[int, float]]:
    """Return (char_pos, time_s) monotonic breakpoints from whisper segments."""
    bps: list[tuple[int, float]] = []
    global_text = ""
    for i, seg in enumerate(segs):
        t = seg["text"].strip()
        gs = len(global_text)
        bps.append((gs, float(seg["start"])))
        bps.append((gs + len(t), float(seg["end"])))
        global_text += t
        if i < len(segs) - 1:
            global_text += " "
    return bps, global_text


def time_at_char(p: int, bps: list[tuple[int, float]]) -> float:
    if p <= bps[0][0]:
        return bps[0][1]
    if p >= bps[-1][0]:
        return bps[-1][1]
    for i in range(len(bps) - 1):
        a_p, a_t = bps[i]
        b_p, b_t = bps[i + 1]
        if a_p <= p <= b_p:
            if b_p == a_p:
                return a_t
            return a_t + (p - a_p) / (b_p - a_p) * (b_t - a_t)
    return bps[-1][1]


def find_sentence_ends(text: str) -> list[int]:
    """Return list of end-exclusive character positions at sentence boundaries."""
    ends: list[int] = []
    for i, ch in enumerate(text):
        if ch not in ".!?":
            continue
        # Decimal numbers: digit . digit — not a sentence end
        if ch == "." and i > 0 and text[i - 1].isdigit():
            if i + 1 < len(text) and text[i + 1].isdigit():
                continue
        # Abbreviations
        if ch == ".":
            preceding = text[max(0, i - 6) : i]
            if _ABBREV_RE.search(preceding):
                continue
            # Single uppercase initial: "U.S." pattern
            if i >= 2 and text[i - 1].isupper() and text[i - 2] in ".- ":
                continue
        # Must be followed by whitespace+uppercase, or end-of-string
        rest = text[i + 1 : i + 5]
        if not rest or re.match(r"\s*$", rest):
            ends.append(i + 1)
        elif re.match(r'[\s"\']+[A-Z]', rest):
            ends.append(i + 1)
    # Always include the very end
    if not ends or ends[-1] < len(text):
        ends.append(len(text))
    return sorted(set(ends))


def split_sentences(
    segs: list[dict],
    min_duration: float = 0.3,
) -> list[dict]:
    bps, global_text = build_breakpoints(segs)
    ends = find_sentence_ends(global_text)

    sentences: list[dict] = []
    prev = 0
    for end in ends:
        raw = global_text[prev:end].strip()
        if not raw:
            prev = end
            continue
        st = time_at_char(prev, bps)
        et = time_at_char(end, bps)
        if et <= st:
            et = st + min_duration
        sentences.append({"start": round(st, 3), "end": round(et, 3), "text": raw})
        prev = end
    return sentences


def main() -> None:
    p = argparse.ArgumentParser(
        description="Split whisper transcript into sentence-level chunks"
    )
    p.add_argument("--transcript", required=True, type=Path,
                   help="transcript_en.json produced by transcribe.py")
    p.add_argument("--out", required=True, type=Path,
                   help="Output path for sentences_en.json")
    args = p.parse_args()

    if not args.transcript.exists():
        sys.exit(f"ERROR: --transcript not found: {args.transcript}")

    segs = json.loads(args.transcript.read_text(encoding="utf-8"))
    sentences = split_sentences(segs)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(sentences, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"[split_sentences] {len(segs)} whisper segments → {len(sentences)} sentences")
    for i, s in enumerate(sentences[:5]):
        print(f"  [{i:3d}] {s['start']:7.2f}s  {s['text'][:90]}")
    if len(sentences) > 5:
        print(f"  ... ({len(sentences) - 5} more)")
    print(f"[split_sentences] wrote {args.out}")


if __name__ == "__main__":
    main()
