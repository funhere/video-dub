# video-dub

[English](README.md) · **中文** · [日本語](README.ja.md) · [한국어](README.ko.md) · [Deutsch](README.de.md) · [Français](README.fr.md) · [Español](README.es.md) · [العربية](README.ar.md)

---

将任意 MP4 视频配音为其他语言，功能包括：

- **ASR 转写** — faster-whisper（完全离线运行）
- **LLM 翻译** — Claude 或 GPT，商务语体，简洁凝练
- **神经网络 TTS** — edge-tts（400+ 语音，无需 API Key）
- **逐段冻结帧同步** — 若 TTS 时长超出原始片段窗口，视频停留在当前段最后一帧，避免级联偏移
- **软字幕** — `mov_text` 流，可在 QuickTime / VLC / mpv 中自由开关

---

## 环境要求

| 工具 | 版本 | 安装方式 |
|------|------|---------|
| Python | ≥ 3.10 | [python.org](https://www.python.org) |
| ffmpeg + ffprobe | ≥ 5.0 | `brew install ffmpeg` / `apt install ffmpeg` |
| ANTHROPIC_API_KEY | — | Claude 翻译所需 |
| OPENAI_API_KEY | — | GPT 翻译所需（可选替代） |

---

## 安装

```bash
git clone <仓库地址> video-dub
cd video-dub
bash install.sh
```

`install.sh` 创建 `.venv/` 虚拟环境并安装所有 Python 依赖。

---

## 快速开始

```bash
# 设置 API Key
export ANTHROPIC_API_KEY=sk-ant-...

# 一条命令完成全流程
.venv/bin/python3 pipeline.py \
  --video  /path/to/source.mp4 \
  --lang   ja \
  --voice  ja-JP-NanamiNeural \
  --out    /path/to/source_ja.mp4
```

输出 MP4 包含：
- 流 0：原始 H.264 视频（含冻结帧）
- 流 1：目标语言 AAC 音频（NanamiNeural @ +15% 语速）
- 流 2：目标语言软字幕（mov_text）

---

## 分步执行

可逐步运行各阶段，便于检查中间结果：

```bash
# Step 1 — 转写（生成 transcript_en.json）
python3 steps/transcribe.py \
  --video  source.mp4 \
  --model  medium \
  --out    work/transcript_en.json

# Step 2 — 翻译（生成 transcript_ja.json）
python3 steps/translate.py \
  --input      work/transcript_en.json \
  --lang       ja \
  --translator claude \
  --out        work/transcript_ja.json

# Step 3 — TTS 合成（生成 work/tts_segments/seg_*.mp3）
python3 steps/synthesize.py \
  --transcript work/transcript_ja.json \
  --voice      ja-JP-NanamiNeural \
  --rate       "+15%" \
  --out-dir    work/tts_segments/

# Step 4 — 拼装（生成 video_joined.mp4、audio_joined.wav、subtitles.srt）
python3 steps/assemble.py \
  --video      source.mp4 \
  --transcript work/transcript_ja.json \
  --tts-dir    work/tts_segments/ \
  --out-dir    work/assembled/

# Step 5 — 合流（生成最终 MP4）
python3 steps/mux.py \
  --video  work/assembled/video_joined.mp4 \
  --audio  work/assembled/audio_joined.wav \
  --srt    work/assembled/subtitles.srt \
  --lang   ja \
  --out    source_ja.mp4
```

---

## 断点续跑

```bash
# 跳过转写，使用已有 JSON
python3 pipeline.py --video source.mp4 \
  --transcript work/transcript_en.json \
  --lang ja --out output.mp4

# 跳过转写 + 翻译
python3 pipeline.py --video source.mp4 \
  --translated work/transcript_ja.json \
  --out output.mp4

# 跳过转写 + 翻译 + TTS
python3 pipeline.py --video source.mp4 \
  --translated work/transcript_ja.json \
  --tts-dir work/tts_segments/ \
  --out output.mp4
```

---

## 主要参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--lang` | `ja` | 目标语言代码 |
| `--voice` | `ja-JP-NanamiNeural` | edge-tts 语音名称 |
| `--rate` | `+15%` | 语速偏移；+15% 为职业播音节奏 |
| `--whisper-model` | `medium` | `tiny` 最快 ↔ `large-v3` 最准 |
| `--translator` | `claude` | `claude` / `openai` / `none` |
| `--style` | *(自动)* | 翻译语体提示词 |
| `--crf` | `22` | x264 质量（18=高质量，28=小文件） |
| `--work-dir` | `<stem>_dub_work/` | 中间文件目录 |

---

## 核心拼装算法

```
对每段 i：
  window  = segs[i+1].start − segs[i].start
  overrun = max(0, tts时长 − window)

  ┌─────────────────────────────────────┐
  │  视频：原始片段（window 秒）         │
  │        + 冻结最后一帧               │  ← 仅当 overrun > 0
  │          （overrun 秒）             │
  └─────────────────────────────────────┘
  ┌─────────────────────────────────────┐
  │  音频：TTS（tts时长 秒）            │
  │        + 静音                       │  ← 仅当 overrun = 0
  │          （window − tts时长 秒）    │
  └─────────────────────────────────────┘

  SRT 时间戳 = 输出时间线累加位置（非原始时间戳）
```

每段完全独立，彻底消除级联偏移问题。

---

## 语音参考

执行 `edge-tts --list-voices` 查看全部 400+ 语音：

| 语言 | 女声 | 男声 |
|------|------|------|
| 日语 | `ja-JP-NanamiNeural` | `ja-JP-KeitaNeural` |
| 普通话 | `zh-CN-XiaoxiaoNeural` | `zh-CN-YunxiNeural` |
| 韩语 | `ko-KR-SunHiNeural` | `ko-KR-InJoonNeural` |
| 英语（美） | `en-US-JennyNeural` | `en-US-GuyNeural` |
| 西班牙语 | `es-ES-ElviraNeural` | `es-ES-AlvaroNeural` |
| 法语 | `fr-FR-DeniseNeural` | `fr-FR-HenriNeural` |
| 德语 | `de-DE-KatjaNeural` | `de-DE-ConradNeural` |

---

## 在 Claude Code 中使用

将 `SKILL.md` 复制到项目的 `.claude/agents/` 目录：

```bash
cp SKILL.md /your/project/.claude/agents/video-dub.md
```

然后在 Claude Code 中说：
> "把 `/path/to/source.mp4` 配音成日语，商务风格。"

Claude 会读取技能文件，解析路径，自动运行 `pipeline.py`。

---

## 项目结构

```
video_dub/
├── SKILL.md          LLM 技能入口
├── README.md         英语文档
├── README.zh.md      本文档
├── requirements.txt  Python 依赖
├── install.sh        一键安装
├── pipeline.py       全流程一键运行
└── steps/
    ├── transcribe.py Step 1：faster-whisper ASR
    ├── translate.py  Step 2：LLM 翻译
    ├── synthesize.py Step 3：edge-tts TTS
    ├── assemble.py   Step 4：逐段拼装（核心）
    └── mux.py        Step 5：最终合流
```

---

## 许可证

Apache 2.0
