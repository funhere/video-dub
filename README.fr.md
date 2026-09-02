# video-dub

[English](README.md) · [中文](README.zh.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Deutsch](README.de.md) · **Français** · [Español](README.es.md) · [العربية](README.ar.md)

---

Doublage de n'importe quelle vidéo MP4 dans une autre langue. Fonctionnalités :

- **Transcription ASR** — faster-whisper (fonctionne entièrement hors ligne)
- **Traduction Agent** — capacité intégrée de l'agent de codage (Claude Code / Codex / IBM Bob), registre professionnel, aucune clé API requise
- **TTS neural** — edge-tts (plus de 400 voix, aucune clé API requise)
- **Synchronisation par image figée** — si la durée TTS dépasse la fenêtre du segment original, la dernière image est figée jusqu'à la fin de la parole, évitant ainsi tout décalage en cascade
- **Sous-titres souples** — flux `mov_text`, activable/désactivable dans QuickTime / VLC / mpv

---

## Prérequis

| Outil | Version | Installation |
|-------|---------|-------------|
| Python | ≥ 3.10 | [python.org](https://www.python.org) |
| ffmpeg + ffprobe | ≥ 5.0 | `brew install ffmpeg` / `apt install ffmpeg` |

---

## Installation

```bash
git clone <URL du dépôt> video-dub
cd video-dub
bash install.sh
```

`install.sh` crée un environnement virtuel `.venv/` et installe toutes les dépendances Python.

---

## Démarrage rapide

```bash
# Phase 1 — transcription + affichage de la tâche de traduction (aucune clé API)
.venv/bin/python3 pipeline.py \
  --video  /chemin/vers/source.mp4 \
  --lang   fr \
  --voice  fr-FR-DeniseNeural

# Le pipeline s'arrête et affiche tous les segments avec les instructions de traduction.
# L'agent (Claude Code / Codex / IBM Bob) traduit et écrit :
#   /chemin/vers/<stem>_dub_work/transcript_fr.json

# Phase 2 — reprendre après la traduction
.venv/bin/python3 pipeline.py \
  --video      /chemin/vers/source.mp4 \
  --translated /chemin/vers/<stem>_dub_work/transcript_fr.json \
  --out        /chemin/vers/source_fr.mp4
```

Le fichier MP4 de sortie contient :
- Flux 0 : vidéo H.264 (avec images figées le cas échéant)
- Flux 1 : audio AAC en français (DeniseNeural @ +15 % de vitesse)
- Flux 2 : sous-titres souples en français (mov_text)

---

## Exécution étape par étape

Chaque étape peut être exécutée indépendamment pour vérifier les résultats intermédiaires :

```bash
# Étape 1 — Transcription (génère transcript_en.json)
python3 steps/transcribe.py \
  --video  source.mp4 \
  --model  medium \
  --out    work/transcript_en.json

# Étape 2 — Traduction (affiche la tâche ; l'agent écrit work/transcript_fr.json)
python3 steps/translate.py \
  --input  work/transcript_en.json \
  --lang   fr \
  --out    work/transcript_fr.json
# → l'agent lit la sortie, traduit et écrit work/transcript_fr.json

# Étape 3 — Synthèse TTS (génère work/tts_segments/seg_*.mp3)
python3 steps/synthesize.py \
  --transcript work/transcript_fr.json \
  --voice      fr-FR-DeniseNeural \
  --rate       "+15%" \
  --out-dir    work/tts_segments/

# Étape 4 — Assemblage (génère video_joined.mp4, audio_joined.wav, subtitles.srt)
python3 steps/assemble.py \
  --video      source.mp4 \
  --transcript work/transcript_fr.json \
  --tts-dir    work/tts_segments/ \
  --out-dir    work/assembled/

# Étape 5 — Multiplexage (génère le MP4 final)
python3 steps/mux.py \
  --video  work/assembled/video_joined.mp4 \
  --audio  work/assembled/audio_joined.wav \
  --srt    work/assembled/subtitles.srt \
  --lang   fr \
  --out    source_fr.mp4
```

---

## Reprise après interruption

```bash
# Ignorer la transcription (utiliser un JSON existant)
python3 pipeline.py --video source.mp4 \
  --transcript work/transcript_en.json \
  --lang fr --out output.mp4

# Ignorer la transcription + traduction
python3 pipeline.py --video source.mp4 \
  --translated work/transcript_fr.json \
  --out output.mp4

# Ignorer la transcription + traduction + TTS
python3 pipeline.py --video source.mp4 \
  --translated work/transcript_fr.json \
  --tts-dir work/tts_segments/ \
  --out output.mp4
```

---

## Options principales

| Option | Valeur par défaut | Description |
|--------|-------------------|-------------|
| `--lang` | `ja` | Code de la langue cible (BCP-47) |
| `--voice` | `ja-JP-NanamiNeural` | Nom de la voix edge-tts |
| `--rate` | `+15%` | Vitesse de parole ; +15 % = rythme de présentateur professionnel |
| `--whisper-model` | `medium` | `tiny` (rapide) ↔ `large-v3` (précis) |
| `--translator` | `native` | `native` (l'agent traduit en interne) / `none` (copier la source) |
| `--style` | *(auto)* | Indication de registre pour le prompt de traduction |
| `--crf` | `22` | Qualité x264 (18 = haute qualité, 28 = fichier léger) |
| `--work-dir` | `<stem>_dub_work/` | Répertoire des fichiers intermédiaires |

---

## Algorithme d'assemblage

```
Pour chaque segment i :
  window  = segs[i+1].start − segs[i].start
  overrun = max(0, durée TTS − window)

  ┌─────────────────────────────────────┐
  │  Vidéo :  clip original (window s)  │
  │           + image figée             │  ← uniquement si overrun > 0
  │             (overrun s)             │
  └─────────────────────────────────────┘
  ┌─────────────────────────────────────┐
  │  Audio :  TTS (durée TTS s)         │
  │           + silence                 │  ← uniquement si overrun = 0
  │             (window − durée TTS s)  │
  └─────────────────────────────────────┘

  Code temporel sous-titre = position cumulée dans la timeline de sortie
```

Chaque segment étant traité indépendamment, aucun décalage en cascade ne peut survenir.

---

## Référence des voix

Exécutez `edge-tts --list-voices` pour voir les 400+ voix disponibles :

| Langue | Féminine | Masculine |
|--------|----------|-----------|
| Japonais | `ja-JP-NanamiNeural` | `ja-JP-KeitaNeural` |
| Chinois (mandarin) | `zh-CN-XiaoxiaoNeural` | `zh-CN-YunxiNeural` |
| Coréen | `ko-KR-SunHiNeural` | `ko-KR-InJoonNeural` |
| Anglais (US) | `en-US-JennyNeural` | `en-US-GuyNeural` |
| Espagnol | `es-ES-ElviraNeural` | `es-ES-AlvaroNeural` |
| Français | `fr-FR-DeniseNeural` | `fr-FR-HenriNeural` |
| Allemand | `de-DE-KatjaNeural` | `de-DE-ConradNeural` |

---

## Utilisation dans Claude Code

Copiez `SKILL.md` dans le répertoire `.claude/agents/` de votre projet :

```bash
cp SKILL.md /votre/projet/.claude/agents/video-dub.md
```

Puis dites dans Claude Code :
> « Doublage de `/chemin/vers/source.mp4` en français professionnel, s'il vous plaît. »

Claude lit le fichier skill, résout les chemins et exécute `pipeline.py` automatiquement.

---

## Structure du projet

```
video_dub/
├── SKILL.md          Point d'entrée skill LLM
├── README.md         Documentation anglaise
├── README.fr.md      Ce fichier
├── requirements.txt  Dépendances Python
├── install.sh        Script d'installation
├── pipeline.py       Pipeline complet en une commande
└── steps/
    ├── transcribe.py Étape 1 : ASR faster-whisper
    ├── translate.py  Étape 2 : traduction Agent intégrée (sans clé API)
    ├── synthesize.py Étape 3 : synthèse TTS edge-tts
    ├── assemble.py   Étape 4 : assemblage par segment (cœur de l'algo)
    └── mux.py        Étape 5 : multiplexage final
```

---

## Licence

Apache 2.0
