#!/usr/bin/env python3
"""
Step 4 — Per-segment assembly: video (with freeze frames) + audio (with silence gaps) + SRT.

Algorithm per segment i:
  window  = segs[i+1].start − segs[i].start   (last seg: video_end − segs[-1].start)
  overrun = max(0, tts_dur − window)

  video clip  = original video [seg.start : seg.start + window]
  if overrun > FREEZE_THRESHOLD:
      video clip += freeze last frame for `overrun` seconds   (tpad filter)

  audio clip  = tts_seg_i.wav
  if overrun ≤ FREEZE_THRESHOLD:
      audio clip += silence(window − tts_dur)   (fills gap to next segment start)

Output:
  {out_dir}/video_joined.mp4
  {out_dir}/audio_joined.wav
  {out_dir}/subtitles.srt     (timestamps in OUTPUT timeline)
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

FREEZE_THRESHOLD = 0.04   # seconds; smaller overruns absorbed as silence


# ── ffprobe helpers ──────────────────────────────────────────────────────────

def probe_dur(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    return float(r.stdout.strip() or "0")


# ── ffmpeg helpers ───────────────────────────────────────────────────────────

def make_silence(dur: float, out: Path, sr: int = 24000) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i",
         f"anullsrc=r={sr}:cl=mono,atrim=duration={dur:.6f}",
         "-ar", str(sr), "-ac", "1", str(out)],
        capture_output=True, check=True,
    )


def mp3_to_wav(src: Path, out: Path, sr: int = 24000) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(src), "-ar", str(sr), "-ac", "1", str(out)],
        capture_output=True, check=True,
    )


def concat_wavs(paths: list[Path], out: Path, tmp: Path) -> None:
    txt = tmp / "concat_wav.txt"
    txt.write_text("\n".join(f"file '{p.resolve()}'" for p in paths))
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(txt),
         "-ar", "24000", "-ac", "1", str(out)],
        capture_output=True, check=True,
    )


def extract_video_seg(
    src: Path, start: float, duration: float,
    freeze: float, out: Path, crf: int,
) -> None:
    vf = f"tpad=stop_mode=clone:stop_duration={freeze:.6f}" if freeze > FREEZE_THRESHOLD else None
    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{start:.6f}", "-t", f"{duration:.6f}", "-i", str(src),
    ]
    if vf:
        cmd += ["-vf", vf, "-c:v", "libx264", "-preset", "fast", "-crf", str(crf)]
    else:
        cmd += ["-c:v", "libx264", "-preset", "fast", "-crf", str(crf)]
    cmd += ["-an", str(out)]
    subprocess.run(cmd, capture_output=True, check=True)


def concat_videos(paths: list[Path], out: Path, tmp: Path) -> None:
    txt = tmp / "concat_vid.txt"
    txt.write_text("\n".join(f"file '{p.resolve()}'" for p in paths))
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(txt),
         "-c:v", "copy", "-an", str(out)],
        capture_output=True, check=True,
    )


# ── SRT helpers ──────────────────────────────────────────────────────────────

def _srt_ts(t: float) -> str:
    t = max(0.0, t)
    h = int(t // 3600); t -= h * 3600
    m = int(t // 60);   t -= m * 60
    s = int(t);         ms = int(round((t - s) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_srt(cues: list[tuple[float, float, str]]) -> str:
    lines = []
    seq = 1
    for start, end, text in cues:
        if text.strip():
            lines.append(f"{seq}\n{_srt_ts(start)} --> {_srt_ts(end)}\n{text.strip()}\n")
            seq += 1
    return "\n".join(lines)


# ── Main assembly ─────────────────────────────────────────────────────────────

def assemble(
    video: Path,
    segs: list[dict],
    mp3s: list[Path],
    out_dir: Path,
    crf: int,
) -> dict:
    tmp = out_dir / "_tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    vid_seg_dir = tmp / "vid_segs"
    aud_seg_dir = tmp / "aud_segs"
    vid_seg_dir.mkdir(exist_ok=True)
    aud_seg_dir.mkdir(exist_ok=True)

    total_video = probe_dur(video)
    tts_durs = [probe_dur(mp3) for mp3 in mp3s]
    n = len(segs)

    # Per-segment metrics
    win_starts = [float(segs[i]["start"]) for i in range(n)]
    win_durs = [
        (float(segs[i + 1]["start"]) if i + 1 < n else total_video) - win_starts[i]
        for i in range(n)
    ]
    overruns  = [max(0.0, tts_durs[i] - win_durs[i]) for i in range(n)]
    extended  = [win_durs[i] + overruns[i] for i in range(n)]

    total_out = sum(extended)
    freeze_count = sum(1 for o in overruns if o > FREEZE_THRESHOLD)
    print(f"[assemble] {n} segments | video={total_video:.1f}s → output={total_out:.1f}s")
    print(f"           freeze-extended: {freeze_count} segs | silence-padded: {n - freeze_count} segs")

    vid_parts: list[Path] = []
    aud_parts: list[Path] = []
    srt_cues:  list[tuple[float, float, str]] = []
    out_cursor = 0.0

    for i, (seg, mp3) in enumerate(zip(segs, mp3s)):
        w_dur    = win_durs[i]
        overrun  = overruns[i]
        tts_dur  = tts_durs[i]
        text     = (seg.get("text") or "").strip()

        # ── video segment ────────────────────────────────────────────────────
        vp = vid_seg_dir / f"v{i:04d}.mp4"
        if not vp.exists():
            extract_video_seg(video, win_starts[i], w_dur, overrun, vp, crf)
        vid_parts.append(vp)

        # ── audio segment ────────────────────────────────────────────────────
        ap = aud_seg_dir / f"a{i:04d}.wav"
        if not ap.exists():
            silence = max(0.0, w_dur - tts_dur)
            tts_wav = aud_seg_dir / f"t{i:04d}.wav"
            mp3_to_wav(mp3, tts_wav)
            if silence > 0.02:
                sil_wav = aud_seg_dir / f"s{i:04d}.wav"
                make_silence(silence, sil_wav)
                concat_wavs([tts_wav, sil_wav], ap, aud_seg_dir)
            else:
                ap = tts_wav   # overrun: TTS fills the full extended window
                # rename so the list is consistent
                ap.rename(aud_seg_dir / f"a{i:04d}.wav")
                ap = aud_seg_dir / f"a{i:04d}.wav"
        aud_parts.append(ap)

        # ── SRT cue (output timeline) ─────────────────────────────────────────
        srt_cues.append((out_cursor, out_cursor + tts_dur, text))
        out_cursor += extended[i]

        if (i + 1) % 10 == 0 or i + 1 == n:
            print(f"  [assemble] {i + 1}/{n} segments")

    # ── Concatenate all video and audio segments ──────────────────────────────
    vid_joined = out_dir / "video_joined.mp4"
    aud_joined = out_dir / "audio_joined.wav"
    srt_path   = out_dir / "subtitles.srt"

    print("[assemble] Concatenating video segments...")
    concat_videos(vid_parts, vid_joined, tmp)

    print("[assemble] Concatenating audio segments...")
    concat_wavs(aud_parts, aud_joined, tmp)

    srt_path.write_text(build_srt(srt_cues), encoding="utf-8")
    print(f"[assemble] SRT: {sum(1 for c in srt_cues if c[2])} cues → {srt_path.name}")

    return {
        "video": vid_joined,
        "audio": aud_joined,
        "srt":   srt_path,
        "total_out_duration": total_out,
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Per-segment video+audio assembly with freeze frames")
    p.add_argument("--video",       required=True, type=Path, help="Original source video")
    p.add_argument("--transcript",  required=True, type=Path, help="Translated segment JSON")
    p.add_argument("--tts-dir",     required=True, type=Path, help="Directory of seg_*.mp3 TTS files")
    p.add_argument("--out-dir",     required=True, type=Path, help="Output directory")
    p.add_argument("--crf",         type=int, default=22,
                   help="x264 CRF for re-encoded segments (18=high quality, 28=smaller)")
    args = p.parse_args()

    for path, name in [(args.video, "--video"), (args.transcript, "--transcript"), (args.tts_dir, "--tts-dir")]:
        if not path.exists():
            sys.exit(f"ERROR: {name} not found: {path}")

    segs = json.loads(args.transcript.read_text(encoding="utf-8"))
    mp3s = sorted(args.tts_dir.glob("seg_*.mp3"))
    if len(mp3s) != len(segs):
        sys.exit(f"ERROR: {len(mp3s)} MP3 files vs {len(segs)} segments (must match)")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    result = assemble(args.video, segs, mp3s, args.out_dir, args.crf)

    print(f"\n[assemble] done")
    print(f"  video → {result['video']}")
    print(f"  audio → {result['audio']}")
    print(f"  srt   → {result['srt']}")
    print(f"  total output duration: {result['total_out_duration']:.2f}s")


if __name__ == "__main__":
    main()
