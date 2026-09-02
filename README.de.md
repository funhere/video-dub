# video-dub

[English](README.md) · [中文](README.zh.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · **Deutsch** · [Français](README.fr.md) · [Español](README.es.md) · [العربية](README.ar.md)

---

Synchronisiert beliebige MP4-Videos in eine andere Sprache. Funktionen:

- **ASR-Transkription** — faster-whisper (vollständig offline)
- **Agent-Übersetzung** — integrierte Fähigkeit des Coding-Agents (Claude Code / Codex / IBM Bob), formeller Businesston, kein API-Schlüssel erforderlich
- **Neuronale TTS** — edge-tts (über 400 Stimmen, kein API-Schlüssel erforderlich)
- **Segmentweises Einfrieren** — Überschreitet die TTS-Audio das Zeitfenster eines Segments, wird das letzte Bild des Segments eingefroren, bis die Sprache abgeschlossen ist. Kein kaskadierender Versatz.
- **Soft-Untertitel** — `mov_text`-Stream, in QuickTime / VLC / mpv ein- und ausschaltbar

---

## Voraussetzungen

| Werkzeug | Version | Installation |
|----------|---------|-------------|
| Python | ≥ 3.10 | [python.org](https://www.python.org) |
| ffmpeg + ffprobe | ≥ 5.0 | `brew install ffmpeg` / `apt install ffmpeg` |

---

## Installation

```bash
git clone <Repository-URL> video-dub
cd video-dub
bash install.sh
```

`install.sh` erstellt eine `.venv/`-Umgebung und installiert alle Python-Abhängigkeiten.

---

## Schnellstart

```bash
# Phase 1 — Transkription + Übersetzungsaufgabe ausgeben (kein API-Schlüssel)
.venv/bin/python3 pipeline.py \
  --video  /pfad/zum/original.mp4 \
  --lang   de \
  --voice  de-DE-KatjaNeural

# Die Pipeline hält an und gibt alle Segmente mit Übersetzungsanweisungen aus.
# Der Agent (Claude Code / Codex / IBM Bob) übersetzt und schreibt:
#   /pfad/zum/<stem>_dub_work/transcript_de.json

# Phase 2 — Nach der Übersetzung fortsetzen
.venv/bin/python3 pipeline.py \
  --video      /pfad/zum/original.mp4 \
  --translated /pfad/zum/<stem>_dub_work/transcript_de.json \
  --out        /pfad/zum/output_de.mp4
```

Die Ausgabe-MP4 enthält:
- Stream 0: H.264-Video (mit eingefrorenen Frames)
- Stream 1: Deutsches AAC-Audio (KatjaNeural @ +15% Geschwindigkeit)
- Stream 2: Deutsche Soft-Untertitel (mov_text)

---

## Schrittweise Ausführung

Jeder Schritt kann einzeln ausgeführt werden, um Zwischenergebnisse zu prüfen:

```bash
# Schritt 1 — Transkription (erzeugt transcript_en.json)
python3 steps/transcribe.py \
  --video  original.mp4 \
  --model  medium \
  --out    work/transcript_en.json

# Schritt 2 — Übersetzung (gibt Aufgabe aus; Agent schreibt work/transcript_de.json)
python3 steps/translate.py \
  --input  work/transcript_en.json \
  --lang   de \
  --out    work/transcript_de.json
# → Agent liest Ausgabe, übersetzt und schreibt work/transcript_de.json

# Schritt 3 — TTS-Synthese (erzeugt work/tts_segments/seg_*.mp3)
python3 steps/synthesize.py \
  --transcript work/transcript_de.json \
  --voice      de-DE-KatjaNeural \
  --rate       "+15%" \
  --out-dir    work/tts_segments/

# Schritt 4 — Assemblierung (erzeugt video_joined.mp4, audio_joined.wav, subtitles.srt)
python3 steps/assemble.py \
  --video      original.mp4 \
  --transcript work/transcript_de.json \
  --tts-dir    work/tts_segments/ \
  --out-dir    work/assembled/

# Schritt 5 — Mux (erzeugt finale MP4)
python3 steps/mux.py \
  --video  work/assembled/video_joined.mp4 \
  --audio  work/assembled/audio_joined.wav \
  --srt    work/assembled/subtitles.srt \
  --lang   de \
  --out    output_de.mp4
```

---

## Fortsetzung nach Unterbrechung

```bash
# Transkription überspringen (vorhandene JSON verwenden)
python3 pipeline.py --video original.mp4 \
  --transcript work/transcript_en.json \
  --lang de --out output.mp4

# Transkription + Übersetzung überspringen
python3 pipeline.py --video original.mp4 \
  --translated work/transcript_de.json \
  --out output.mp4

# Transkription + Übersetzung + TTS überspringen
python3 pipeline.py --video original.mp4 \
  --translated work/transcript_de.json \
  --tts-dir work/tts_segments/ \
  --out output.mp4
```

---

## Wichtige Optionen

| Flag | Standard | Beschreibung |
|------|----------|--------------|
| `--lang` | `ja` | Zielsprachcode (BCP-47) |
| `--voice` | `ja-JP-NanamiNeural` | edge-tts Stimmenname |
| `--rate` | `+15%` | Sprechgeschwindigkeit; +15% = professionelles Sprechtempo |
| `--whisper-model` | `medium` | `tiny` (schnell) ↔ `large-v3` (präzise) |
| `--translator` | `native` | `native` (Agent übersetzt intern) / `none` (Quelle kopieren) |
| `--style` | *(auto)* | Ton-/Registerhinweis für den Übersetzungsprompt |
| `--crf` | `22` | x264-Qualität (18=hohe Qualität, 28=kleine Datei) |
| `--work-dir` | `<stem>_dub_work/` | Verzeichnis für Zwischendateien |

---

## Assemblierungsalgorithmus

```
Für jedes Segment i:
  window  = segs[i+1].start − segs[i].start
  overrun = max(0, TTS-Dauer − window)

  ┌─────────────────────────────────────┐
  │  Video:  Originalclip (window Sek.) │
  │          + letztes Bild einfrieren  │  ← nur wenn overrun > 0
  │            (overrun Sek.)           │
  └─────────────────────────────────────┘
  ┌─────────────────────────────────────┐
  │  Audio:  TTS (TTS-Dauer Sek.)       │
  │          + Stille                   │  ← nur wenn overrun = 0
  │            (window − TTS-Dauer Sek.)│
  └─────────────────────────────────────┘

  Untertitel-Zeitcode = kumulierte Position in der Ausgabe-Zeitleiste
```

Da jedes Segment unabhängig verarbeitet wird, entsteht kein kaskadierender Versatz.

---

## Stimmenübersicht

`edge-tts --list-voices` zeigt alle 400+ verfügbaren Stimmen:

| Sprache | Weiblich | Männlich |
|---------|----------|----------|
| Japanisch | `ja-JP-NanamiNeural` | `ja-JP-KeitaNeural` |
| Chinesisch (Mandarin) | `zh-CN-XiaoxiaoNeural` | `zh-CN-YunxiNeural` |
| Koreanisch | `ko-KR-SunHiNeural` | `ko-KR-InJoonNeural` |
| Englisch (US) | `en-US-JennyNeural` | `en-US-GuyNeural` |
| Spanisch | `es-ES-ElviraNeural` | `es-ES-AlvaroNeural` |
| Französisch | `fr-FR-DeniseNeural` | `fr-FR-HenriNeural` |
| Deutsch | `de-DE-KatjaNeural` | `de-DE-ConradNeural` |

---

## Verwendung in Claude Code

Kopieren Sie `SKILL.md` in das Verzeichnis `.claude/agents/` Ihres Projekts:

```bash
cp SKILL.md /ihr/projekt/.claude/agents/video-dub.md
```

Sagen Sie dann in Claude Code:
> „Bitte `/pfad/zur/quelle.mp4` in professionellem Deutsch synchronisieren."

Claude liest die Skill-Datei, löst die Pfade auf und führt `pipeline.py` automatisch aus.

---

## Projektstruktur

```
video_dub/
├── SKILL.md          LLM-Skill-Einstiegspunkt
├── README.md         Englische Dokumentation
├── README.de.md      Diese Datei
├── requirements.txt  Python-Abhängigkeiten
├── install.sh        Einrichtungsskript
├── pipeline.py       Gesamtpipeline in einem Befehl
└── steps/
    ├── transcribe.py Schritt 1: faster-whisper ASR
    ├── translate.py  Schritt 2: Agent-Übersetzung (kein API-Schlüssel)
    ├── synthesize.py Schritt 3: edge-tts TTS
    ├── assemble.py   Schritt 4: Segmentweise Assemblierung (Kernalgorithmus)
    └── mux.py        Schritt 5: Finaler Mux
```

---

## Lizenz

Apache 2.0
