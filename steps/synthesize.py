#!/usr/bin/env python3
"""
Step 3 — Synthesize TTS audio for each segment.

Supported providers:
  edge-tts   (default) Microsoft neural voices, no API key required
  elevenlabs  ElevenLabs voice cloning / custom voices, requires API key
  cosyvoice   Alibaba CosyVoice, voice cloning from reference audio (local or API)

Produces: {out_dir}/seg_0000.mp3 … seg_NNNN.mp3
"""
import argparse
import asyncio
import json
import subprocess
import sys
from pathlib import Path


# ── Provider: edge-tts ────────────────────────────────────────────────────────

async def _edge_synth_one(edge_tts, text: str, voice: str, rate: str,
                          out: Path, retries: int = 5) -> None:
    for attempt in range(retries):
        try:
            comm = edge_tts.Communicate(text=text, voice=voice, rate=rate)
            await comm.save(str(out))
            return
        except Exception as e:
            if attempt == retries - 1:
                raise
            wait = 2 ** attempt
            print(f"  [synthesize] retry {attempt+1}/{retries-1} ({e.__class__.__name__}), waiting {wait}s…")
            await asyncio.sleep(wait)


async def _synth_edge(segs: list[dict], voice: str, rate: str, out_dir: Path) -> None:
    try:
        import edge_tts
    except ImportError:
        sys.exit("ERROR: edge-tts not installed. Run: pip install edge-tts")

    for idx, seg in enumerate(segs):
        out = out_dir / f"seg_{idx:04d}.mp3"
        if out.exists() and out.stat().st_size > 0:
            continue
        if out.exists():
            out.unlink()
        text = (seg.get("text") or "").strip()
        if text:
            await _edge_synth_one(edge_tts, text, voice, rate, out)
        else:
            _silence(out)
        if (idx + 1) % 10 == 0 or idx + 1 == len(segs):
            print(f"  [synthesize] {idx+1}/{len(segs)} segments")


# ── Provider: ElevenLabs ──────────────────────────────────────────────────────

def _synth_elevenlabs(segs: list[dict], voice_id: str, model: str,
                      out_dir: Path, api_key: str) -> None:
    """
    voice_id: ElevenLabs voice ID (from web UI or after cloning)
    model:    e.g. "eleven_multilingual_v2" (best for Chinese/non-English)
              or   "eleven_turbo_v2_5" (faster, lower latency)
    """
    try:
        from elevenlabs.client import ElevenLabs
    except ImportError:
        sys.exit("ERROR: elevenlabs not installed. Run: pip install elevenlabs")

    client = ElevenLabs(api_key=api_key)

    for idx, seg in enumerate(segs):
        out = out_dir / f"seg_{idx:04d}.mp3"
        if out.exists() and out.stat().st_size > 0:
            continue
        if out.exists():
            out.unlink()
        text = (seg.get("text") or "").strip()
        if text:
            audio = client.text_to_speech.convert(
                voice_id=voice_id,
                text=text,
                model_id=model,
                output_format="mp3_44100_128",
            )
            with open(out, "wb") as f:
                for chunk in audio:
                    f.write(chunk)
        else:
            _silence(out)
        if (idx + 1) % 10 == 0 or idx + 1 == len(segs):
            print(f"  [synthesize] {idx+1}/{len(segs)} segments")


# ── Provider: CosyVoice (via ModelScope API or local) ─────────────────────────

def _synth_cosyvoice(segs: list[dict], ref_audio: str, ref_text: str,
                     out_dir: Path, api_key: str | None) -> None:
    """
    ref_audio: path to reference audio file (3–30s, clean speech)
    ref_text:  transcript of the reference audio (improves quality)

    Supports two backends:
      - ModelScope API (api_key provided): no GPU needed
      - Local CosyVoice (api_key=None):   requires local install + GPU
    """
    if api_key:
        _synth_cosyvoice_api(segs, ref_audio, ref_text, out_dir, api_key)
    else:
        _synth_cosyvoice_local(segs, ref_audio, ref_text, out_dir)


def _synth_cosyvoice_api(segs, ref_audio, ref_text, out_dir, api_key):
    try:
        from modelscope.pipelines import pipeline
    except ImportError:
        sys.exit("ERROR: modelscope not installed. Run: pip install modelscope")

    import io
    tts = pipeline(
        task="text-to-speech",
        model="iic/CosyVoice2-0.5B",
        model_revision="v2.0.0",
    )
    for idx, seg in enumerate(segs):
        out = out_dir / f"seg_{idx:04d}.mp3"
        if out.exists() and out.stat().st_size > 0:
            continue
        text = (seg.get("text") or "").strip()
        if text:
            result = tts(
                text,
                voice=ref_audio,
                reference_text=ref_text,
            )
            wav_bytes = result["output_wav"]
            # Convert WAV bytes → MP3 via ffmpeg pipe
            subprocess.run(
                ["ffmpeg", "-y", "-f", "wav", "-i", "pipe:0",
                 "-c:a", "libmp3lame", "-q:a", "2", str(out)],
                input=wav_bytes, capture_output=True, check=True,
            )
        else:
            _silence(out)
        if (idx + 1) % 10 == 0 or idx + 1 == len(segs):
            print(f"  [synthesize] {idx+1}/{len(segs)} segments")


def _synth_cosyvoice_local(segs, ref_audio, ref_text, out_dir):
    try:
        import torchaudio
        from cosyvoice.cli.cosyvoice import CosyVoice2
    except ImportError:
        sys.exit(
            "ERROR: CosyVoice not installed locally.\n"
            "  See: https://github.com/FunAudioLLM/CosyVoice\n"
            "  Or use --cosyvoice-api-key for ModelScope API (no GPU needed)."
        )

    import torch
    model = CosyVoice2("pretrained_models/CosyVoice2-0.5B")
    prompt_speech, sr = torchaudio.load(ref_audio)

    for idx, seg in enumerate(segs):
        out = out_dir / f"seg_{idx:04d}.mp3"
        if out.exists() and out.stat().st_size > 0:
            continue
        text = (seg.get("text") or "").strip()
        if text:
            result = model.inference_zero_shot(
                tts_text=text,
                prompt_text=ref_text,
                prompt_speech_16k=torchaudio.functional.resample(prompt_speech, sr, 16000),
                stream=False,
            )
            wav = next(result)["tts_speech"]
            with open(out, "wb") as f:
                subprocess.run(
                    ["ffmpeg", "-y", "-f", "f32le", "-ar", "22050", "-ac", "1",
                     "-i", "pipe:0", "-c:a", "libmp3lame", "-q:a", "2", str(out)],
                    input=wav.numpy().tobytes(), capture_output=True, check=True,
                )
        else:
            _silence(out)
        if (idx + 1) % 10 == 0 or idx + 1 == len(segs):
            print(f"  [synthesize] {idx+1}/{len(segs)} segments")


# ── Shared util ───────────────────────────────────────────────────────────────

def _silence(out: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i",
         "anullsrc=r=24000:cl=mono,atrim=duration=0.1", str(out)],
        capture_output=True, check=True,
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    p = argparse.ArgumentParser(
        description="Synthesize TTS audio for each transcript segment",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Provider examples:

  # edge-tts (default, no API key)
  synthesize.py --transcript t.json --out-dir tts/ \\
    --voice zh-CN-YunjianNeural --rate "+15%"

  # ElevenLabs voice clone
  synthesize.py --transcript t.json --out-dir tts/ \\
    --provider elevenlabs \\
    --elevenlabs-voice-id <voice_id> \\
    --elevenlabs-api-key  $ELEVENLABS_API_KEY \\
    --elevenlabs-model    eleven_multilingual_v2

  # CosyVoice (local or ModelScope API)
  synthesize.py --transcript t.json --out-dir tts/ \\
    --provider cosyvoice \\
    --ref-audio  /path/to/speaker.mp3 \\
    --ref-text   "Reference audio transcript here."
        """,
    )
    p.add_argument("--transcript", required=True, type=Path)
    p.add_argument("--out-dir",    required=True, type=Path)

    # Provider selection
    p.add_argument("--provider", default="edge-tts",
                   choices=["edge-tts", "elevenlabs", "cosyvoice"],
                   help="TTS backend (default: edge-tts)")

    # edge-tts options
    p.add_argument("--voice", default="ja-JP-NanamiNeural",
                   help="[edge-tts] Voice name (run 'edge-tts --list-voices')")
    p.add_argument("--rate",  default="+15%",
                   help="[edge-tts] Speech rate offset, e.g. +15%%")

    # ElevenLabs options
    p.add_argument("--elevenlabs-voice-id", default=None,
                   help="[elevenlabs] Voice ID from ElevenLabs dashboard or after cloning")
    p.add_argument("--elevenlabs-api-key",  default=None,
                   help="[elevenlabs] API key (or set ELEVENLABS_API_KEY env var)")
    p.add_argument("--elevenlabs-model",    default="eleven_multilingual_v2",
                   help="[elevenlabs] Model ID (default: eleven_multilingual_v2)")

    # CosyVoice options
    p.add_argument("--ref-audio", default=None,
                   help="[cosyvoice] Reference audio file for voice cloning (3–30s)")
    p.add_argument("--ref-text",  default="",
                   help="[cosyvoice] Transcript of the reference audio")
    p.add_argument("--cosyvoice-api-key", default=None,
                   help="[cosyvoice] ModelScope API key (omit to use local model)")

    args = p.parse_args()

    if not args.transcript.exists():
        sys.exit(f"ERROR: transcript not found: {args.transcript}")

    segs = json.loads(args.transcript.read_text(encoding="utf-8"))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    print(f"[synthesize] {len(segs)} segments, provider={args.provider}")

    if args.provider == "edge-tts":
        print(f"[synthesize] voice={args.voice}, rate={args.rate}")
        asyncio.run(_synth_edge(segs, args.voice, args.rate, args.out_dir))

    elif args.provider == "elevenlabs":
        import os
        api_key = args.elevenlabs_api_key or os.environ.get("ELEVENLABS_API_KEY")
        if not api_key:
            sys.exit("ERROR: --elevenlabs-api-key or ELEVENLABS_API_KEY env var required")
        if not args.elevenlabs_voice_id:
            sys.exit("ERROR: --elevenlabs-voice-id required")
        print(f"[synthesize] voice_id={args.elevenlabs_voice_id}, model={args.elevenlabs_model}")
        _synth_elevenlabs(segs, args.elevenlabs_voice_id, args.elevenlabs_model,
                          args.out_dir, api_key)

    elif args.provider == "cosyvoice":
        if not args.ref_audio:
            sys.exit("ERROR: --ref-audio required for cosyvoice provider")
        print(f"[synthesize] ref_audio={args.ref_audio}")
        _synth_cosyvoice(segs, args.ref_audio, args.ref_text,
                         args.out_dir, args.cosyvoice_api_key)

    print(f"[synthesize] done — {len(segs)} MP3 files in {args.out_dir}")


if __name__ == "__main__":
    main()
