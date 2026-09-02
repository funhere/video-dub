# video-dub

[English](README.md) · [中文](README.zh.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Deutsch](README.de.md) · [Français](README.fr.md) · **Español** · [العربية](README.ar.md)

---

Doblaje de cualquier vídeo MP4 a otro idioma. Características:

- **Transcripción ASR** — faster-whisper (funciona completamente sin conexión)
- **Traducción Agent** — capacidad integrada del agente de codificación (Claude Code / Codex / IBM Bob), registro profesional formal, sin clave API
- **TTS neuronal** — edge-tts (más de 400 voces, sin clave API)
- **Sincronización por fotograma congelado** — si la duración del TTS supera la ventana del segmento original, el último fotograma se congela hasta que finaliza la locución, eliminando el desplazamiento en cascada
- **Subtítulos blandos** — flujo `mov_text`, activable/desactivable en QuickTime / VLC / mpv

---

## Requisitos

| Herramienta | Versión | Instalación |
|-------------|---------|-------------|
| Python | ≥ 3.10 | [python.org](https://www.python.org) |
| ffmpeg + ffprobe | ≥ 5.0 | `brew install ffmpeg` / `apt install ffmpeg` |

---

## Instalación

```bash
git clone <URL del repositorio> video-dub
cd video-dub
bash install.sh
```

`install.sh` crea un entorno virtual `.venv/` e instala todas las dependencias de Python.

---

## Inicio rápido

```bash
# Fase 1 — transcripción + mostrar tarea de traducción (sin clave API)
.venv/bin/python3 pipeline.py \
  --video  /ruta/al/original.mp4 \
  --lang   es \
  --voice  es-ES-ElviraNeural

# El pipeline se detiene y muestra todos los segmentos con instrucciones de traducción.
# El agente (Claude Code / Codex / IBM Bob) traduce y escribe:
#   /ruta/al/<stem>_dub_work/transcript_es.json

# Fase 2 — continuar tras la traducción
.venv/bin/python3 pipeline.py \
  --video      /ruta/al/original.mp4 \
  --translated /ruta/al/<stem>_dub_work/transcript_es.json \
  --out        /ruta/al/original_es.mp4
```

El archivo MP4 de salida contiene:
- Flujo 0: vídeo H.264 (con fotogramas congelados donde sea necesario)
- Flujo 1: audio AAC en español (ElviraNeural @ +15 % de velocidad)
- Flujo 2: subtítulos blandos en español (mov_text)

---

## Ejecución paso a paso

Cada paso puede ejecutarse de forma independiente para revisar los resultados intermedios:

```bash
# Paso 1 — Transcripción (genera transcript_en.json)
python3 steps/transcribe.py \
  --video  original.mp4 \
  --model  medium \
  --out    work/transcript_en.json

# Paso 2 — Traducción (muestra tarea; el agente escribe work/transcript_es.json)
python3 steps/translate.py \
  --input  work/transcript_en.json \
  --lang   es \
  --out    work/transcript_es.json
# → el agente lee la salida, traduce y escribe work/transcript_es.json

# Paso 3 — Síntesis TTS (genera work/tts_segments/seg_*.mp3)
python3 steps/synthesize.py \
  --transcript work/transcript_es.json \
  --voice      es-ES-ElviraNeural \
  --rate       "+15%" \
  --out-dir    work/tts_segments/

# Paso 4 — Ensamblaje (genera video_joined.mp4, audio_joined.wav, subtitles.srt)
python3 steps/assemble.py \
  --video      original.mp4 \
  --transcript work/transcript_es.json \
  --tts-dir    work/tts_segments/ \
  --out-dir    work/assembled/

# Paso 5 — Multiplexación (genera el MP4 final)
python3 steps/mux.py \
  --video  work/assembled/video_joined.mp4 \
  --audio  work/assembled/audio_joined.wav \
  --srt    work/assembled/subtitles.srt \
  --lang   es \
  --out    original_es.mp4
```

---

## Reanudación tras interrupción

```bash
# Omitir transcripción (usar JSON existente)
python3 pipeline.py --video original.mp4 \
  --transcript work/transcript_en.json \
  --lang es --out output.mp4

# Omitir transcripción + traducción
python3 pipeline.py --video original.mp4 \
  --translated work/transcript_es.json \
  --out output.mp4

# Omitir transcripción + traducción + TTS
python3 pipeline.py --video original.mp4 \
  --translated work/transcript_es.json \
  --tts-dir work/tts_segments/ \
  --out output.mp4
```

---

## Opciones principales

| Opción | Valor por defecto | Descripción |
|--------|-------------------|-------------|
| `--lang` | `ja` | Código del idioma destino (BCP-47) |
| `--voice` | `ja-JP-NanamiNeural` | Nombre de la voz edge-tts |
| `--rate` | `+15%` | Velocidad de locución; +15 % = ritmo de presentador profesional |
| `--whisper-model` | `medium` | `tiny` (rápido) ↔ `large-v3` (preciso) |
| `--translator` | `native` | `native` (el agente traduce) / `none` (copiar fuente) |
| `--style` | *(auto)* | Indicación de registro para el prompt de traducción |
| `--crf` | `22` | Calidad x264 (18=alta calidad, 28=archivo pequeño) |
| `--work-dir` | `<stem>_dub_work/` | Directorio de archivos intermedios |

---

## Algoritmo de ensamblaje

```
Para cada segmento i:
  window  = segs[i+1].start − segs[i].start
  overrun = max(0, duración TTS − window)

  ┌─────────────────────────────────────┐
  │  Vídeo:  clip original (window s)   │
  │          + congelar último fotograma│  ← solo si overrun > 0
  │            (overrun s)              │
  └─────────────────────────────────────┘
  ┌─────────────────────────────────────┐
  │  Audio:  TTS (duración TTS s)       │
  │          + silencio                 │  ← solo si overrun = 0
  │            (window − dur. TTS s)    │
  └─────────────────────────────────────┘

  Código de tiempo subtítulo = posición acumulada en la línea de tiempo de salida
```

Cada segmento se procesa de forma independiente, por lo que no se produce ningún desplazamiento en cascada.

---

## Referencia de voces

Ejecute `edge-tts --list-voices` para ver las más de 400 voces disponibles:

| Idioma | Femenina | Masculina |
|--------|----------|-----------|
| Japonés | `ja-JP-NanamiNeural` | `ja-JP-KeitaNeural` |
| Chino (mandarín) | `zh-CN-XiaoxiaoNeural` | `zh-CN-YunxiNeural` |
| Coreano | `ko-KR-SunHiNeural` | `ko-KR-InJoonNeural` |
| Inglés (EE. UU.) | `en-US-JennyNeural` | `en-US-GuyNeural` |
| Español | `es-ES-ElviraNeural` | `es-ES-AlvaroNeural` |
| Francés | `fr-FR-DeniseNeural` | `fr-FR-HenriNeural` |
| Alemán | `de-DE-KatjaNeural` | `de-DE-ConradNeural` |

---

## Uso en Claude Code

Copie `SKILL.md` en el directorio `.claude/agents/` de su proyecto:

```bash
cp SKILL.md /su/proyecto/.claude/agents/video-dub.md
```

A continuación, indique en Claude Code:
> «Por favor, dobla `/ruta/al/original.mp4` al español profesional.»

Claude leerá el archivo skill, resolverá las rutas y ejecutará `pipeline.py` automáticamente.

---

## Estructura del proyecto

```
video_dub/
├── SKILL.md          Punto de entrada del skill LLM
├── README.md         Documentación en inglés
├── README.es.md      Este archivo
├── requirements.txt  Dependencias de Python
├── install.sh        Script de instalación
├── pipeline.py       Pipeline completo en un comando
└── steps/
    ├── transcribe.py Paso 1: ASR faster-whisper
    ├── translate.py  Paso 2: traducción Agent integrada (sin clave API)
    ├── synthesize.py Paso 3: síntesis TTS edge-tts
    ├── assemble.py   Paso 4: ensamblaje por segmento (algoritmo central)
    └── mux.py        Paso 5: multiplexación final
```

---

## Licencia

Apache 2.0
