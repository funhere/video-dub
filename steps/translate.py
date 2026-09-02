#!/usr/bin/env python3
"""
Step 2 — Translate timestamped segments with an LLM.

Supports:
  --translator claude   (ANTHROPIC_API_KEY)
  --translator openai   (OPENAI_API_KEY)
  --translator none     (copy source JSON; fill in translations manually)

Output preserves segment count, start/end timestamps, and JSON structure.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

CHUNK = 25  # segments per API call

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
}


def _build_system(lang: str, style: str | None) -> str:
    defaults = LANG_DEFAULTS.get(lang, {"name": lang, "style": "Formal business register", "mora_rate": 5})
    return SYSTEM_TEMPLATE.format(
        lang_name=defaults["name"],
        style=style or defaults["style"],
        mora_rate=defaults["mora_rate"],
    )


def _parse_raw(raw: str, fallback: list[dict]) -> list[dict]:
    raw = re.sub(r"^```[a-z]*\n?", "", raw.strip()).rstrip("`").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        print(f"  [WARN] JSON parse failed — keeping originals for this chunk")
        return fallback


def translate_claude(segs: list[dict], lang: str, style: str | None, model: str) -> list[dict]:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        sys.exit("ERROR: ANTHROPIC_API_KEY not set")
    try:
        import anthropic
    except ImportError:
        sys.exit("ERROR: anthropic package not installed")

    client = anthropic.Anthropic(api_key=api_key)
    system = _build_system(lang, style)
    result = []

    for i in range(0, len(segs), CHUNK):
        chunk = segs[i : i + CHUNK]
        msg = client.messages.create(
            model=model,
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": json.dumps(chunk, ensure_ascii=False, indent=2)}],
        )
        result.extend(_parse_raw(msg.content[0].text, chunk))
        print(f"  [translate/claude] {min(i + CHUNK, len(segs))}/{len(segs)} segments")

    return result


def translate_openai(segs: list[dict], lang: str, style: str | None, model: str) -> list[dict]:
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        sys.exit("ERROR: OPENAI_API_KEY not set")
    try:
        from openai import OpenAI
    except ImportError:
        sys.exit("ERROR: openai package not installed")

    client = OpenAI(api_key=api_key)
    system = _build_system(lang, style)
    result = []

    for i in range(0, len(segs), CHUNK):
        chunk = segs[i : i + CHUNK]
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(chunk, ensure_ascii=False, indent=2)},
            ],
            max_tokens=4096,
        )
        result.extend(_parse_raw(resp.choices[0].message.content or "", chunk))
        print(f"  [translate/openai] {min(i + CHUNK, len(segs))}/{len(segs)} segments")

    return result


def main() -> None:
    p = argparse.ArgumentParser(description="Translate subtitle segments with an LLM")
    p.add_argument("--input",       required=True, type=Path, help="Source JSON (transcript_en.json)")
    p.add_argument("--out",         required=True, type=Path, help="Output JSON path")
    p.add_argument("--lang",        default="ja",  help="Target language code (ja/zh/ko/en/es/fr/de/pt)")
    p.add_argument("--style",       default=None,  help="Override register/tone hint for the prompt")
    p.add_argument("--translator",  default="claude", choices=["claude", "openai", "none"])
    p.add_argument("--claude-model",default="claude-opus-4-5")
    p.add_argument("--openai-model",default="gpt-4o")
    args = p.parse_args()

    if not args.input.exists():
        sys.exit(f"ERROR: input not found: {args.input}")

    segs = json.loads(args.input.read_text(encoding="utf-8"))
    print(f"[translate] {len(segs)} segments, target={args.lang}, translator={args.translator}")

    if args.translator == "claude":
        translated = translate_claude(segs, args.lang, args.style, args.claude_model)
    elif args.translator == "openai":
        translated = translate_openai(segs, args.lang, args.style, args.openai_model)
    else:
        print("[translate] translator=none — copying source JSON (fill in translations manually)")
        translated = segs

    if len(translated) != len(segs):
        print(f"  [WARN] segment count mismatch: got {len(translated)}, expected {len(segs)}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(translated, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[translate] done → {args.out}")


if __name__ == "__main__":
    main()
