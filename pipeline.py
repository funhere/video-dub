#!/usr/bin/env python3
"""
video-dub pipeline — dub any MP4 into another language.

Usage (full auto):
  python3 pipeline.py --video source.mp4 --lang ja --out source_ja.mp4

Usage (resume from translated JSON):
  python3 pipeline.py --video source.mp4 --translated work/transcript_ja.json

Usage (step flags):
  python3 pipeline.py --video source.mp4 --lang ja \\
      --skip-transcribe --transcript work/transcript_en.json \\
      --out source_ja.mp4
"""
import argparse
import json
import sys
from pathlib import Path


def _step(label: str) -> None:
    print(f"\n{'═'*60}")
    print(f"  {label}")
    print(f"{'═'*60}")


def main() -> None:
    p = argparse.ArgumentParser(
        description="video-dub: dub MP4 into another language with freeze-aligned subtitles",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # I/O
    p.add_argument("--video",      required=True, type=Path, help="Source MP4")
    p.add_argument("--out",        type=Path, default=None,  help="Output MP4 (default: <stem>_<lang>.mp4)")
    p.add_argument("--work-dir",   type=Path, default=None,
                   help="Working directory for intermediates (default: <stem>_dub_work/)")

    # Skip / supply precomputed artifacts
    p.add_argument("--skip-transcribe", action="store_true")
    p.add_argument("--transcript",      type=Path, default=None,
                   help="Pre-existing source-language JSON (implies --skip-transcribe)")
    p.add_argument("--skip-translate",  action="store_true")
    p.add_argument("--translated",      type=Path, default=None,
                   help="Pre-existing translated JSON (implies --skip-translate)")
    p.add_argument("--skip-synthesize", action="store_true")
    p.add_argument("--tts-dir",         type=Path, default=None,
                   help="Pre-existing TTS MP3 directory (implies --skip-synthesize)")

    # Step 1 — transcribe
    p.add_argument("--whisper-model", default="medium",
                   choices=["tiny", "base", "small", "medium", "large-v2", "large-v3"])
    p.add_argument("--source-lang",   default=None, help="Force source language code (e.g. en)")

    # Step 2 — translate
    p.add_argument("--lang",        default="ja",    help="Target language BCP-47 (ja/zh/ko/en/…)")
    p.add_argument("--style",       default=None,    help="Register/tone override for translation prompt")
    p.add_argument("--translator",  default="claude", choices=["claude", "openai", "none"])
    p.add_argument("--claude-model",default="claude-opus-4-5")
    p.add_argument("--openai-model",default="gpt-4o")

    # Step 3 — synthesize
    p.add_argument("--voice", default="ja-JP-NanamiNeural",
                   help="edge-tts voice name")
    p.add_argument("--rate",  default="+15%",
                   help="Speech rate offset (e.g. +15%% or -10%%)")

    # Step 4 — assemble
    p.add_argument("--crf", type=int, default=22,
                   help="x264 CRF for re-encoded segments (18=high quality, 28=smaller)")

    args = p.parse_args()

    # Resolve paths
    video = args.video.resolve()
    if not video.exists():
        sys.exit(f"ERROR: video not found: {video}")

    work = (args.work_dir or video.parent / f"{video.stem}_dub_work").resolve()
    work.mkdir(parents=True, exist_ok=True)

    out = (args.out or video.parent / f"{video.stem}_{args.lang}.mp4").resolve()

    # Imply skips from supplied artifacts
    if args.transcript:
        args.skip_transcribe = True
    if args.translated:
        args.skip_translate = True
    if args.tts_dir:
        args.skip_synthesize = True

    # ── Step 1: Transcribe ────────────────────────────────────────────────────
    transcript_en = args.transcript or (work / "transcript_en.json")
    if not args.skip_transcribe:
        _step("Step 1/5 — Transcribe (faster-whisper)")
        from steps.transcribe import transcribe
        segs = transcribe(video, args.whisper_model, args.source_lang)
        transcript_en.write_text(json.dumps(segs, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[pipeline] transcript → {transcript_en}")
    else:
        if not transcript_en.exists():
            sys.exit(f"ERROR: --transcript not found: {transcript_en}")
        print(f"[pipeline] skip transcribe — using {transcript_en}")

    # ── Step 2: Translate ─────────────────────────────────────────────────────
    transcript_lang = args.translated or (work / f"transcript_{args.lang}.json")
    if not args.skip_translate:
        _step(f"Step 2/5 — Translate → {args.lang}  ({args.translator})")
        segs_en = json.loads(transcript_en.read_text(encoding="utf-8"))
        if args.translator == "claude":
            from steps.translate import translate_claude
            translated = translate_claude(segs_en, args.lang, args.style, args.claude_model)
        elif args.translator == "openai":
            from steps.translate import translate_openai
            translated = translate_openai(segs_en, args.lang, args.style, args.openai_model)
        else:
            print("[pipeline] translator=none — copying source, fill translations manually")
            translated = segs_en
        transcript_lang.write_text(json.dumps(translated, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[pipeline] translated → {transcript_lang}")
    else:
        if not transcript_lang.exists():
            sys.exit(f"ERROR: --translated not found: {transcript_lang}")
        print(f"[pipeline] skip translate — using {transcript_lang}")

    segs = json.loads(transcript_lang.read_text(encoding="utf-8"))

    # ── Step 3: Synthesize TTS ────────────────────────────────────────────────
    tts_dir = args.tts_dir or (work / "tts_segments")
    if not args.skip_synthesize:
        _step(f"Step 3/5 — Synthesize TTS  voice={args.voice}  rate={args.rate}")
        import asyncio
        from steps.synthesize import _synth_all
        tts_dir.mkdir(parents=True, exist_ok=True)
        asyncio.run(_synth_all(segs, args.voice, args.rate, tts_dir))
        print(f"[pipeline] TTS → {tts_dir}")
    else:
        if not tts_dir.exists():
            sys.exit(f"ERROR: --tts-dir not found: {tts_dir}")
        print(f"[pipeline] skip synthesize — using {tts_dir}")

    # ── Step 4: Assemble ──────────────────────────────────────────────────────
    _step("Step 4/5 — Assemble (per-segment video + audio + SRT)")
    from steps.assemble import assemble
    assembled_dir = work / "assembled"
    assembled_dir.mkdir(exist_ok=True)
    mp3s = sorted(tts_dir.glob("seg_*.mp3"))
    if len(mp3s) != len(segs):
        sys.exit(f"ERROR: {len(mp3s)} MP3 files vs {len(segs)} segments")

    result = assemble(video, segs, mp3s, assembled_dir, args.crf)

    # ── Step 5: Mux ───────────────────────────────────────────────────────────
    _step("Step 5/5 — Mux final MP4")
    from steps.mux import mux
    title = {"ja": "日本語", "zh": "中文", "ko": "한국어", "en": "English"}.get(args.lang, args.lang)
    mux(result["video"], result["audio"], result["srt"], out, args.lang, title)

    size_mb = out.stat().st_size / 1024 ** 2
    print(f"\n{'═'*60}")
    print(f"  ✅  Done: {out}")
    print(f"      Size: {size_mb:.1f} MB")
    print(f"      Work: {work}")
    print(f"{'═'*60}\n")


if __name__ == "__main__":
    main()
