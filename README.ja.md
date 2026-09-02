# video-dub

[English](README.md) · [中文](README.zh.md) · **日本語** · [한국어](README.ko.md) · [Deutsch](README.de.md) · [Français](README.fr.md) · [Español](README.es.md) · [العربية](README.ar.md)

---

任意の MP4 動画を他の言語に吹き替えるツールです。

- **ASR 文字起こし** — faster-whisper（完全オフライン動作）
- **Agent 翻訳** — コーディング Agent（Claude Code / Codex / IBM Bob）の内蔵機能を使用、ビジネス敬語、API Key 不要
- **ニューラル TTS** — edge-tts（400 以上のボイス、API Key 不要）
- **セグメント単位フリーズフレーム同期** — TTS 音声がセグメント時間窓を超過した場合、映像を最終フレームで停止して音声完了を待機（カスケードずれを防止）
- **ソフト字幕** — `mov_text` ストリーム（QuickTime / VLC / mpv でオン/オフ切替可能）

---

## 動作要件

| ツール | バージョン | インストール |
|--------|-----------|------------|
| Python | ≥ 3.10 | [python.org](https://www.python.org) |
| ffmpeg + ffprobe | ≥ 5.0 | `brew install ffmpeg` / `apt install ffmpeg` |

---

## インストール

```bash
git clone <リポジトリ URL> video-dub
cd video-dub
bash install.sh
```

`install.sh` が `.venv/` 仮想環境を作成し、必要な Python パッケージをすべてインストールします。

---

## クイックスタート

```bash
# フェーズ 1 — 文字起こし + 翻訳タスク表示（API Key 不要）
.venv/bin/python3 pipeline.py \
  --video  /path/to/source.mp4 \
  --lang   ja \
  --voice  ja-JP-NanamiNeural

# パイプラインが一時停止し、全セグメントと翻訳指示を表示します。
# Agent（Claude Code / Codex / IBM Bob）が翻訳して書き込みます：
#   /path/to/<stem>_dub_work/transcript_ja.json

# フェーズ 2 — 翻訳完了後に再開
.venv/bin/python3 pipeline.py \
  --video      /path/to/source.mp4 \
  --translated /path/to/<stem>_dub_work/transcript_ja.json \
  --out        /path/to/source_ja.mp4
```

出力 MP4 には次のストリームが含まれます：
- ストリーム 0：H.264 映像（フリーズフレームを含む）
- ストリーム 1：日本語 AAC 音声（NanamiNeural @ +15% レート）
- ストリーム 2：日本語ソフト字幕（mov_text）

---

## ステップ別実行

各ステップを個別に実行して中間生成物を確認できます：

```bash
# Step 1 — 文字起こし（transcript_en.json を生成）
python3 steps/transcribe.py \
  --video  source.mp4 \
  --model  medium \
  --out    work/transcript_en.json

# Step 2 — 翻訳（タスク表示；agent が work/transcript_ja.json を書き込む）
python3 steps/translate.py \
  --input  work/transcript_en.json \
  --lang   ja \
  --out    work/transcript_ja.json
# → agent が出力を読み、翻訳して work/transcript_ja.json を書き込む

# Step 3 — TTS 合成（work/tts_segments/seg_*.mp3 を生成）
python3 steps/synthesize.py \
  --transcript work/transcript_ja.json \
  --voice      ja-JP-NanamiNeural \
  --rate       "+15%" \
  --out-dir    work/tts_segments/

# Step 4 — アセンブル（video_joined.mp4、audio_joined.wav、subtitles.srt を生成）
python3 steps/assemble.py \
  --video      source.mp4 \
  --transcript work/transcript_ja.json \
  --tts-dir    work/tts_segments/ \
  --out-dir    work/assembled/

# Step 5 — マルチプレックス（最終 MP4 を生成）
python3 steps/mux.py \
  --video  work/assembled/video_joined.mp4 \
  --audio  work/assembled/audio_joined.wav \
  --srt    work/assembled/subtitles.srt \
  --lang   ja \
  --out    source_ja.mp4
```

---

## 途中再開

```bash
# 文字起こしをスキップ（既存 JSON を使用）
python3 pipeline.py --video source.mp4 \
  --transcript work/transcript_en.json \
  --lang ja --out output.mp4

# 文字起こし + 翻訳をスキップ
python3 pipeline.py --video source.mp4 \
  --translated work/transcript_ja.json \
  --out output.mp4

# 文字起こし + 翻訳 + TTS をスキップ
python3 pipeline.py --video source.mp4 \
  --translated work/transcript_ja.json \
  --tts-dir work/tts_segments/ \
  --out output.mp4
```

---

## 主なオプション

| フラグ | デフォルト | 説明 |
|--------|-----------|------|
| `--lang` | `ja` | 目標言語コード（BCP-47） |
| `--voice` | `ja-JP-NanamiNeural` | edge-tts ボイス名 |
| `--rate` | `+15%` | 発話速度；+15% がプロのナレーターのペース |
| `--whisper-model` | `medium` | `tiny`（高速） ↔ `large-v3`（高精度） |
| `--translator` | `native` | `native`（agent 内蔵翻訳） / `none`（ソースをコピー） |
| `--style` | *(自動)* | 翻訳の語調プロンプト |
| `--crf` | `22` | x264 品質（18=高品質、28=小ファイル） |
| `--work-dir` | `<stem>_dub_work/` | 中間ファイル保存先 |

---

## アセンブルアルゴリズム

```
各セグメント i に対して：
  window  = segs[i+1].start − segs[i].start
  overrun = max(0, TTS 長 − window)

  ┌─────────────────────────────────────┐
  │  映像：元クリップ（window 秒）       │
  │        + 最終フレーム停止           │  ← overrun > 0 のみ
  │          （overrun 秒）             │
  └─────────────────────────────────────┘
  ┌─────────────────────────────────────┐
  │  音声：TTS（TTS 長 秒）             │
  │        + 無音                       │  ← overrun = 0 のみ
  │          （window − TTS 長 秒）     │
  └─────────────────────────────────────┘

  字幕タイムコード = 出力タイムライン上の累積位置
```

各セグメントは完全に独立して処理されるため、カスケードずれが発生しません。

---

## ボイス一覧

`edge-tts --list-voices` で全 400 以上のボイスを確認できます：

| 言語 | 女性 | 男性 |
|------|------|------|
| 日本語 | `ja-JP-NanamiNeural` | `ja-JP-KeitaNeural` |
| 中国語（普通話） | `zh-CN-XiaoxiaoNeural` | `zh-CN-YunxiNeural` |
| 韓国語 | `ko-KR-SunHiNeural` | `ko-KR-InJoonNeural` |
| 英語（米国） | `en-US-JennyNeural` | `en-US-GuyNeural` |
| スペイン語 | `es-ES-ElviraNeural` | `es-ES-AlvaroNeural` |
| フランス語 | `fr-FR-DeniseNeural` | `fr-FR-HenriNeural` |
| ドイツ語 | `de-DE-KatjaNeural` | `de-DE-ConradNeural` |

---

## Claude Code での使用方法

`SKILL.md` をプロジェクトの `.claude/agents/` ディレクトリにコピーしてください：

```bash
cp SKILL.md /your/project/.claude/agents/video-dub.md
```

Claude Code で次のように指示するだけです：
> 「`/path/to/source.mp4` をビジネス敬語の日本語に吹き替えてください。」

Claude がスキルファイルを読み込み、パスを解決して `pipeline.py` を自動実行します。

---

## プロジェクト構成

```
video_dub/
├── SKILL.md          LLM スキルエントリポイント
├── README.md         英語ドキュメント
├── README.ja.md      本ドキュメント
├── requirements.txt  Python 依存パッケージ
├── install.sh        セットアップスクリプト
├── pipeline.py       全工程一括実行
└── steps/
    ├── transcribe.py Step 1：faster-whisper ASR
    ├── translate.py  Step 2：Agent 内蔵翻訳（API Key 不要）
    ├── synthesize.py Step 3：edge-tts TTS 合成
    ├── assemble.py   Step 4：逐段アセンブル（コアアルゴリズム）
    └── mux.py        Step 5：最終マルチプレックス
```

---

## ライセンス

Apache 2.0
