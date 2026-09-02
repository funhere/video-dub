#!/usr/bin/env python3
"""
Step 5 — Mux: merge rebuilt video, dubbed audio, and burned-in subtitles into final MP4.

Subtitle modes:
  hard (default) — burn subtitles into video frames via drawtext; always visible
  soft            — mov_text soft track; player must enable manually
  both            — burn in (always visible) + keep soft track for search/copy

Root cause of the original bug: mov_text is a soft subtitle stream.
Most players (QuickTime, Chrome, mobile) do not auto-enable it.
Hard burn guarantees subtitles are always shown.
"""
import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_LANG_MAP = {
    "ja": "jpn", "zh": "chi", "ko": "kor", "en": "eng",
    "es": "spa", "fr": "fra", "de": "deu", "pt": "por",
    "it": "ita", "ru": "rus", "ar": "ara", "hi": "hin",
}

# Language → font file path (IBM Plex covers CJK cleanly; fallback to system)
_FONT_PATHS: list[tuple[str, str]] = [
    # (path, supported_langs_regex)
    ("/Library/Fonts/IBM-Plex-Sans-JP/unhinted/IBMPlexSansJP-Medium.otf",    "ja"),
    ("/Library/Fonts/IBM-Plex-Sans-SC/unhinted/IBMPlexSansSC-Regular.otf",    "zh"),
    ("/Library/Fonts/IBM-Plex-Sans-KR/IBMPlexSansKR-Medium.otf",              "ko"),
    ("/System/Library/Fonts/Supplemental/Arial Unicode MS.ttf",               "ar|hi|ru"),
    # Broad fallbacks
    ("/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",                         "ja"),
    ("/System/Library/Fonts/STHeiti Medium.ttc",                               "zh"),
    ("/System/Library/Fonts/AppleSDGothicNeo.ttc",                            "ko"),
    ("/System/Library/Fonts/Supplemental/Arial.ttf",                          "en|es|fr|de|pt|it"),
]

_LINUX_FONTS: dict[str, list[str]] = {
    "ja": ["/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
           "/usr/share/fonts/truetype/noto/NotoSansCJKjp-Regular.otf"],
    "zh": ["/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"],
    "ko": ["/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"],
    "default": ["/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"],
}


def _find_font(lang: str) -> str:
    for path, langs in _FONT_PATHS:
        if re.search(langs, lang) and Path(path).exists():
            return path
    # Linux fallback
    for p in _LINUX_FONTS.get(lang, []) + _LINUX_FONTS["default"]:
        if Path(p).exists():
            return p
    raise FileNotFoundError(
        f"No suitable font found for lang='{lang}'. "
        "Install a Unicode font or specify --font-file."
    )


def _srt_to_ms(ts: str) -> float:
    h, m, rest = ts.strip().split(":")
    s, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def _parse_srt(srt: Path) -> list[tuple[float, float, str]]:
    cues: list[tuple[float, float, str]] = []
    for block in re.split(r"\n{2,}", srt.read_text(encoding="utf-8").strip()):
        lines = block.strip().splitlines()
        if len(lines) < 3 or " --> " not in lines[1]:
            continue
        s, e = lines[1].split(" --> ")
        text = " ".join(lines[2:]).strip()
        if text:
            cues.append((_srt_to_ms(s), _srt_to_ms(e), text))
    return cues


def _escape_drawtext(text: str) -> str:
    """Escape text for ffmpeg drawtext filter value."""
    text = text.replace("\\", "\\\\")
    text = text.replace("'",  "’")   # curly apostrophe avoids shell quoting issues
    text = text.replace(":",  "\\:")
    text = text.replace("%",  "\\%")
    return text


def _build_drawtext_filter(
    cues: list[tuple[float, float, str]],
    font_file: str,
    font_size: int,
    tmp_dir: Path,
) -> str:
    """
    Build a chained drawtext filter string.
    Each cue writes its text to a temp file (avoids shell-escaping issues).
    """
    parts: list[str] = []
    for idx, (start, end, text) in enumerate(cues):
        # Write text to temp file — sidesteps all escaping problems
        txt_file = tmp_dir / f"sub_{idx:04d}.txt"
        txt_file.write_text(text, encoding="utf-8")

        ff = font_file.replace(":", "\\:")   # escape colon in font path
        tf = str(txt_file).replace(":", "\\:")

        part = (
            f"drawtext="
            f"fontfile={ff}:"
            f"textfile={tf}:"
            f"fontsize={font_size}:"
            f"fontcolor=white:"
            f"borderw=2:"
            f"bordercolor=black@0.9:"
            f"box=1:"
            f"boxcolor=black@0.35:"
            f"boxborderw=6:"
            f"x=(w-tw)/2:"
            f"y=h-th-40:"
            f"enable='between(t,{start:.3f},{end:.3f})'"
        )
        parts.append(part)

    return ",".join(parts)


def _burn_subtitles(
    video: Path,
    cues: list[tuple[float, float, str]],
    font_file: str,
    font_size: int,
    out: Path,
    tmp_dir: Path,
    crf: int,
) -> None:
    vf = _build_drawtext_filter(cues, font_file, font_size, tmp_dir)
    r = subprocess.run(
        ["ffmpeg", "-y", "-i", str(video),
         "-vf", vf,
         "-c:v", "libx264", "-preset", "fast", "-crf", str(crf),
         "-an", str(out)],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(f"Subtitle burn failed:\n{r.stderr[-800:]}")


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
    subtitle_mode: str,
    font_file: str | None,
    font_size: int,
    crf: int,
) -> None:
    iso_lang = _LANG_MAP.get(lang, lang)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = out.parent / "_mux_tmp"
    tmp_dir.mkdir(exist_ok=True)

    try:
        # ── Resolve font ──────────────────────────────────────────────────────
        if subtitle_mode != "soft":
            resolved_font = font_file or _find_font(lang)
            print(f"[mux] font: {resolved_font}")
            cues = _parse_srt(srt)
            print(f"[mux] {len(cues)} subtitle cues")

        # ── Step A: burn subtitles into video (hard / both) ──────────────────
        if subtitle_mode in ("hard", "both"):
            print(f"[mux] Burning subtitles ({subtitle_mode} mode)…")
            burned_video = tmp_dir / "video_burned.mp4"
            _burn_subtitles(video, cues, resolved_font, font_size, burned_video, tmp_dir, crf)
            video_for_mux = burned_video
        else:
            video_for_mux = video

        # ── Step B: mux audio ─────────────────────────────────────────────────
        with_audio = tmp_dir / "with_audio.mp4"
        r = subprocess.run(
            ["ffmpeg", "-y",
             "-i", str(video_for_mux), "-i", str(audio),
             "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
             "-map", "0:v:0", "-map", "1:a:0", "-shortest",
             str(with_audio)],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            sys.exit(f"ERROR (audio mux):\n{r.stderr[-600:]}")

        # ── Step C: add soft subtitle stream (soft / both) ───────────────────
        if subtitle_mode in ("soft", "both"):
            r = subprocess.run(
                ["ffmpeg", "-y",
                 "-i", str(with_audio), "-i", str(srt),
                 "-c:v", "copy", "-c:a", "copy", "-c:s", "mov_text",
                 "-metadata:s:s:0", f"language={iso_lang}",
                 "-metadata:s:s:0", f"title={title}",
                 str(out)],
                capture_output=True, text=True,
            )
            if r.returncode != 0:
                sys.exit(f"ERROR (subtitle mux):\n{r.stderr[-600:]}")
        else:
            shutil.move(str(with_audio), str(out))

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def main() -> None:
    p = argparse.ArgumentParser(
        description="Mux video + audio + subtitles into final MP4",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Subtitle modes:
  hard  (default) burn into video — always visible in any player
  soft            mov_text track — player must enable manually
  both            burn in + keep soft track
        """,
    )
    p.add_argument("--video",          required=True, type=Path)
    p.add_argument("--audio",          required=True, type=Path)
    p.add_argument("--srt",            required=True, type=Path)
    p.add_argument("--out",            required=True, type=Path)
    p.add_argument("--lang",           default="ja")
    p.add_argument("--title",          default=None)
    p.add_argument("--subtitle-mode",  default="hard",
                   choices=["hard", "soft", "both"])
    p.add_argument("--font-file",      default=None,
                   help="Override font file path (auto-detected per language if omitted)")
    p.add_argument("--font-size",      type=int, default=28)
    p.add_argument("--crf",            type=int, default=20,
                   help="x264 CRF for subtitle burn re-encode (default 20)")
    args = p.parse_args()

    for path, flag in [(args.video, "--video"), (args.audio, "--audio"), (args.srt, "--srt")]:
        if not path.exists():
            sys.exit(f"ERROR: {flag} not found: {path}")

    title = args.title or {"ja": "日本語", "zh": "中文", "ko": "한국어", "en": "English",
                           "de": "Deutsch", "fr": "Français", "es": "Español",
                           "ar": "العربية"}.get(args.lang, args.lang)

    print(f"[mux] video={args.video.name} ({_probe_dur(args.video):.1f}s)")
    print(f"[mux] audio={args.audio.name} ({_probe_dur(args.audio):.1f}s)")
    print(f"[mux] mode={args.subtitle_mode}  lang={args.lang}  font_size={args.font_size}")

    mux(args.video, args.audio, args.srt, args.out,
        args.lang, title, args.subtitle_mode,
        args.font_file, args.font_size, args.crf)

    size_mb = args.out.stat().st_size / 1024 ** 2
    dur = _probe_dur(args.out)
    mode_desc = {"hard": "burned-in (always visible)",
                 "soft": "soft track (player toggle)",
                 "both": "burned-in + soft track"}[args.subtitle_mode]
    print(f"\n[mux] ✅ {args.out}")
    print(f"      Duration: {dur:.1f}s  Size: {size_mb:.1f} MB")
    print(f"      Subtitles: {mode_desc}")


if __name__ == "__main__":
    main()
