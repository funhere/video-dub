#!/usr/bin/env python3
"""
Step 2 — Translate timestamped segments using the calling coding agent.

Native mode (default): prints a structured translation task so the calling
agent (Claude Code / Codex / IBM Bob / …) can translate with its built-in
capabilities — no external API key required.

None mode (--translator none): copies source segments unchanged.

Workflow for native mode:
  1. Run pipeline.py normally (or this script standalone).
  2. The pipeline prints the translation task and exits cleanly.
  3. The agent translates the segments and writes transcript_{lang}.json.
  4. Resume: pipeline.py --translated work/transcript_{lang}.json …
"""
import argparse
import json
import sys
from pathlib import Path

SYSTEM_TEMPLATE = """\
You are a professional video localization expert for enterprise software products.
Translate the following JSON array of subtitle segments into {lang_name}.

Rules:
- Register: {style}
- Preserve all product names / brand names verbatim: WatsonX, IBM, AI, API, LLM, SaaS, etc.
- Technical terms may stay in English or be introduced as "日本語訳（English）" once.
- Keep exact segment count and order.
- Each segment: fit the translation within approximately 1.5× the original (end−start) seconds
  at a natural speech pace of {mora_rate} mora/s.
- Output ONLY a JSON array — no markdown, no explanation.
  Format: [{{"start":…,"end":…,"text":"…"}},…]
"""

LANG_DEFAULTS: dict[str, dict] = {
    "ja": {"name": "Japanese (です・ます体、敬語)", "style": "Formal keigo (です・ます), polite business", "mora_rate": 7},
    "zh": {"name": "Simplified Chinese (书面语，您)", "style": "Formal written Chinese, use 您", "mora_rate": 5},
    "ko": {"name": "Korean (합쇼체 존댓말)", "style": "Formal polite Korean (합쇼체)", "mora_rate": 7},
    "en": {"name": "English (professional)", "style": "Professional presenter voice", "mora_rate": 3},
    "es": {"name": "Spanish (usted, formal)", "style": "Formal business Spanish", "mora_rate": 4},
    "fr": {"name": "French (vouvoiement, formel)", "style": "Formal business French", "mora_rate": 4},
    "de": {"name": "German (Sie, formell)", "style": "Formal business German", "mora_rate": 4},
    "pt": {"name": "Portuguese (você, formal)", "style": "Formal business Portuguese", "mora_rate": 4},
    "ar": {"name": "Arabic (Modern Standard Arabic, formal)", "style": "Formal MSA business register", "mora_rate": 4},
}


def _build_system(lang: str, style: str | None) -> str:
    defaults = LANG_DEFAULTS.get(lang, {"name": lang, "style": "Formal business register", "mora_rate": 5})
    return SYSTEM_TEMPLATE.format(
        lang_name=defaults["name"],
        style=style or defaults["style"],
        mora_rate=defaults["mora_rate"],
    )


def translate_native(segs: list[dict], lang: str, style: str | None, out_path: Path) -> None:
    """
    Print a structured translation task for the calling agent, then exit.

    The agent should:
      1. Translate every segment following the system prompt below.
      2. Write the result JSON to out_path.
      3. Resume the pipeline with --translated <out_path>.
    """
    defaults = LANG_DEFAULTS.get(lang, {"name": lang, "style": "Formal business register", "mora_rate": 5})
    system = _build_system(lang, style)
    sep = "═" * 60

    print(f"\n{sep}")
    print("  ACTION REQUIRED — Native Translation Task")
    print(sep)
    print(f"\nTarget language : {defaults['name']}  (code: {lang})")
    print(f"Style           : {style or defaults['style']}")
    print(f"Speech pace     : {defaults['mora_rate']} mora/s target")
    print(f"Output file     : {out_path}")
    print(f"\n{'─' * 60}")
    print("SYSTEM PROMPT:")
    print(system)
    print(f"{'─' * 60}")
    print(f"SEGMENTS ({len(segs)} total):")
    print(json.dumps(segs, ensure_ascii=False, indent=2))
    print(f"{'─' * 60}")
    print("\nINSTRUCTIONS FOR THE AGENT:")
    print("  1. Translate every segment above following the system prompt.")
    print('  2. Keep the exact JSON structure: [{"start":…,"end":…,"text":"…"},…]')
    print(f"  3. Preserve segment count exactly: {len(segs)} segments.")
    print(f"  4. Write the translated JSON to:\n       {out_path}")
    print(f"  5. Resume the pipeline:\n")
    print(f"       python3 pipeline.py --video <source.mp4> \\")
    print(f"         --translated {out_path} --out <output.mp4>")
    print(f"\n{sep}\n")
    sys.exit(0)


def main() -> None:
    p = argparse.ArgumentParser(
        description="Translate subtitle segments (native agent mode — no API key required)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Translators:
  native  (default) — print translation task for the calling agent; no API key needed
  none              — copy source segments unchanged (fill in translations manually)
        """,
    )
    p.add_argument("--input",      required=True, type=Path, help="Source JSON (transcript_en.json)")
    p.add_argument("--out",        required=True, type=Path, help="Output JSON path (agent will write here)")
    p.add_argument("--lang",       default="ja",  help="Target language code (ja/zh/ko/en/es/fr/de/pt/ar)")
    p.add_argument("--style",      default=None,  help="Override register/tone hint for the prompt")
    p.add_argument("--translator", default="native", choices=["native", "none"])
    args = p.parse_args()

    if not args.input.exists():
        sys.exit(f"ERROR: input not found: {args.input}")

    segs = json.loads(args.input.read_text(encoding="utf-8"))
    print(f"[translate] {len(segs)} segments, target={args.lang}, translator={args.translator}")

    if args.translator == "native":
        translate_native(segs, args.lang, args.style, args.out.resolve())
        # translate_native calls sys.exit — execution stops here
    else:
        print("[translate] translator=none — copying source segments (fill in translations manually)")
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(segs, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[translate] done → {args.out}")


if __name__ == "__main__":
    main()
