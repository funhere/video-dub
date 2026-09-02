#!/usr/bin/env python3
"""
Step 5 — Mux: merge rebuilt video, dubbed audio, and soft subtitle into final MP4.

Output streams:
  0: H.264 video  (stream copy — no re-encode)
  1: AAC audio    (192 kbps)
  2: mov_text     (soft subtitle, toggleable in QuickTime / VLC / mpv)
"""
import argparse
import subprocess
import sys
from pathlib import Path

# BCP-47 → ISO 639-2/T mapping for mov_text language metadata
_LANG_MAP = {
    "ja": "jpn", "zh": "chi", "ko": "kor", "en": "eng",
    "es": "spa", "fr": "fra", "de": "deu", "pt": "por",
    "it": "ita", "ru": "rus", "ar": "ara", "hi": "hin",
}


def _probe_dur(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    return float(r.stdout.strip() or "0")


def mux(
    video: Path,
    audio: Path,
    srt: Path,
    out: Path,
    lang: str,
    title: str,
) -> None:
    iso_lang = _LANG_MAP.get(lang, lang)

    # Step A: replace audio track
    tmp_no_sub = out.parent / (out.stem + "_nosub.mp4")
    r = subprocess.run(
        ["ffmpeg", "-y",
         "-i", str(video), "-i", str(audio),
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
         "-map", "0:v:0", "-map", "1:a:0", "-shortest",
         str(tmp_no_sub)],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        sys.exit(f"ERROR (audio mux):\n{r.stderr[-600:]}")

    # Step B: add soft subtitle stream
    r = subprocess.run(
        ["ffmpeg", "-y",
         "-i", str(tmp_no_sub), "-i", str(srt),
         "-c:v", "copy", "-c:a", "copy", "-c:s", "mov_text",
         "-metadata:s:s:0", f"language={iso_lang}",
         "-metadata:s:s:0", f"title={title}",
         str(out)],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        sys.exit(f"ERROR (subtitle mux):\n{r.stderr[-600:]}")

    tmp_no_sub.unlink(missing_ok=True)


def main() -> None:
    p = argparse.ArgumentParser(description="Mux video + audio + subtitle into final MP4")
    p.add_argument("--video",  required=True, type=Path, help="Assembled video (no audio)")
    p.add_argument("--audio",  required=True, type=Path, help="Dubbed audio WAV")
    p.add_argument("--srt",    required=True, type=Path, help="Subtitle SRT file")
    p.add_argument("--out",    required=True, type=Path, help="Output MP4 path")
    p.add_argument("--lang",   default="ja",  help="Target language BCP-47 code (ja/zh/ko/en/…)")
    p.add_argument("--title",  default=None,  help="Subtitle track title (default: language name)")
    args = p.parse_args()

    for path, flag in [(args.video, "--video"), (args.audio, "--audio"), (args.srt, "--srt")]:
        if not path.exists():
            sys.exit(f"ERROR: {flag} not found: {path}")

    title = args.title or {"ja": "日本語", "zh": "中文", "ko": "한국어", "en": "English"}.get(args.lang, args.lang)
    args.out.parent.mkdir(parents=True, exist_ok=True)

    print(f"[mux] video={args.video.name} ({_probe_dur(args.video):.1f}s)")
    print(f"[mux] audio={args.audio.name} ({_probe_dur(args.audio):.1f}s)")
    print(f"[mux] lang={args.lang}  title={title}")

    mux(args.video, args.audio, args.srt, args.out, args.lang, title)

    size_mb = args.out.stat().st_size / 1024 ** 2
    dur = _probe_dur(args.out)
    print(f"\n[mux] ✅ {args.out}")
    print(f"      Duration: {dur:.1f}s ({dur/60:.1f} min)  Size: {size_mb:.1f} MB")
    print(f"      Streams: video(H.264) + audio(AAC) + subtitle(mov_text/{_LANG_MAP.get(args.lang, args.lang)})")


if __name__ == "__main__":
    main()
