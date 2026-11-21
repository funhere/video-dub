# video-dub

[English](README.md) · [中文](README.zh.md) · **日本語** · [한국어](README.ko.md) · [Deutsch](README.de.md) · [Français](README.fr.md) · [Español](README.es.md) · [العربية](README.ar.md)

---

任意の動画を、次の機能で他言語に吹き替えます。

- **ASR 文字起こし** — faster-whisper（完全オフラインで動作）
- **Agent 翻訳** — コーディング Agent（Claude Code / Codex / IBM Bob）の内蔵機能を使用。ビジネス文体に対応し、API キーは不要
- **ニューラル TTS** — edge-tts（400 以上のボイス、API キー不要）
- **セグメント単位のフリーズフレーム同期** — TTS 音声がセグメントの時間枠を超過した場合、映像の最終フレームを静止させて音声の完了を待つため、ずれが累積しません
- **ソフト字幕** — `mov_text` ストリーム（QuickTime / VLC / mpv でオン/オフを切り替え可能）
<img width="1200" height="628" alt="image" src="https://github.com/user-attachments/assets/4f98af96-8e0b-48ff-8367-0f9fdc9a2acb" />
video-dub は 5 つのステップで構成されます。青い Step 2 だけを AI エージェントが担当します
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
# フェーズ 1 — 文字起こし + 翻訳タスクの表示（API キー不要）
.venv/bin/python3 pipeline.py \
  --video  /path/to/source.mp4 \
  --lang   ja \
  --voice  ja-JP-NanamiNeural

# パイプラインは一時停止し、全セグメントと翻訳指示を表示します。
# Agent（Claude Code / Codex / IBM Bob）が翻訳し、次のファイルに書き込みます：
#   /path/to/<stem>_dub_work/transcript_ja.json

# フェーズ 2 — 翻訳完了後に再開
.venv/bin/python3 pipeline.py \
  --video      /path/to/source.mp4 \
  --translated /path/to/<stem>_dub_work/transcript_ja.json \
  --out        /path/to/source_ja.mp4
```

出力される MP4 には、次のストリームが含まれます：
- ストリーム 0：H.264 映像（フリーズフレームを含む）
- ストリーム 1：日本語 AAC 音声（NanamiNeural @ +15% レート）
- ストリーム 2：日本語ソフト字幕（mov_text）

---

## ステップ別実行

各ステップを個別に実行し、中間生成物を確認できます：

```bash
# Step 1 — 文字起こし（transcript_en.json を生成）
python3 steps/transcribe.py \
  --video  source.mp4 \
  --model  medium \
  --out    work/transcript_en.json

# Step 2 — 翻訳（タスクを表示。Agent が work/transcript_ja.json を書き込む）
python3 steps/translate.py \
  --input  work/transcript_en.json \
  --lang   ja \
  --out    work/transcript_ja.json
# → Agent が出力を読み取って翻訳し、work/transcript_ja.json に書き込む

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

# Step 5 — 多重化（mux）（最終 MP4 を生成）
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
# 文字起こしをスキップ（既存の JSON を使用）
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
| `--lang` | `ja` | ターゲット言語コード（BCP-47） |
| `--voice` | `ja-JP-NanamiNeural` | edge-tts のボイス名 |
| `--rate` | `+15%` | 発話速度。+15% はプロのナレーターに近いペース |
| `--whisper-model` | `medium` | `tiny`（高速） ↔ `large-v3`（高精度） |
| `--translator` | `native` | `native`（Agent 内蔵翻訳） / `none`（原文をそのままコピー） |
| `--style` | *(自動)* | 翻訳の文体を指定するプロンプト |
| `--crf` | `22` | x264 の品質（18＝高品質、28＝小サイズ） |
| `--work-dir` | `<stem>_dub_work/` | 中間ファイルの保存先 |

---

## アセンブルアルゴリズム
<img width="1200" height="628" alt="image" src="https://github.com/user-attachments/assets/e42a4440-e4a0-4a3a-aee0-608d4ca3b1a0" />
TTS が短ければ無音で埋め、長ければ映像の最終フレームを静止させます

```
各セグメント i に対して：
  window  = segs[i+1].start − segs[i].start
  overrun = max(0, TTS 長 − window)

  ┌─────────────────────────────────────┐
  │  映像：元クリップ（window 秒）          │
  │        + 最終フレーム停止              │  ← overrun > 0 のみ
  │          （overrun 秒）              │
  └─────────────────────────────────────┘
  ┌─────────────────────────────────────┐
  │  音声：TTS（TTS 長 秒）               │
  │        + 無音                       │  ← overrun = 0 のみ
  │          （window − TTS 長 秒）      │
  └─────────────────────────────────────┘

  字幕タイムコード = 出力タイムライン上の累積位置
```

シーケンシャルな開始位置合わせによる累積的なタイミングずれを解消します。各セグメントは独立しており、動画は無音部分を含めて自然に再生するか、フリーズフレームで延長します。字幕のタイミングは、最終出力のタイムラインに基づいて再計算します。

---

## ボイス一覧

`edge-tts --list-voices` で、400 以上のボイスすべてを確認できます：

| 言語 | 女性 | 男性 |
|------|------|------|
| 日本語 | `ja-JP-NanamiNeural` | `ja-JP-KeitaNeural` |
| 中国語（普通話） | `zh-CN-XiaoxiaoNeural` | `zh-CN-YunxiNeural` |
| 韓国語 | `ko-KR-SunHiNeural` | `ko-KR-InJoonNeural` |
| 英語（米国） | `en-US-JennyNeural` | `en-US-GuyNeural` |
| スペイン語 | `es-ES-ElviraNeural` | `es-ES-AlvaroNeural` |
| フランス語 | `fr-FR-DeniseNeural` | `fr-FR-HenriNeural` |
| ドイツ語 | `de-DE-KatjaNeural` | `de-DE-ConradNeural` |

**中国語ボイス（スタイル別）：**

| ボイス | 性別 | スタイル |
|--------|------|----------|
| `zh-CN-YunjianNeural` | 男性 | 落ち着いた低音——ドキュメンタリー向き |
| `zh-CN-YunyangNeural` | 男性 | ニュースキャスター調 |
| `zh-CN-YunxiNeural` | 男性 | 明るく会話的 |
| `zh-CN-XiaoxiaoNeural` | 女性 | 汎用・自然 |
| `zh-CN-XiaoyiNeural` | 女性 | 表現力豊か・温かみあり |

**`--rate` ガイド：**

| 値 | 効果 |
|----|------|
| `0%` | デフォルト（やや遅め） |
| `+10%` | 自然で聴きやすい |
| `+15%` | 推奨——プロのナレーターペース |
| `+20%` | 速め、内容の濃いコンテンツ向き |
| `-10%` | 遅め、チュートリアル向き |

---

## カスタムボイス

自分の声や特定の話者の声でクローンを作成できます。2 つの方法があります：

### オプション A — ElevenLabs（最も簡単、クラウド）

```bash
pip install elevenlabs
```

```python
# 一度だけ実行：声のクローンを作成
from elevenlabs.client import ElevenLabs
client = ElevenLabs(api_key="YOUR_KEY")   # elevenlabs.io で無料取得
voice = client.clone(name="my-voice", files=["my_recording.mp3"])
print("voice_id:", voice.voice_id)        # この ID を保存してください
```

```bash
# クローンしたボイスを使用
python3 steps/synthesize.py \
  --transcript work/transcript_ja.json \
  --out-dir    work/tts/ \
  --provider   elevenlabs \
  --elevenlabs-voice-id  <voice_id> \
  --elevenlabs-api-key   $ELEVENLABS_API_KEY \
  --elevenlabs-model     eleven_multilingual_v2
```

**録音のヒント：** 静かな部屋で 1〜3 分、明瞭に話す、BGM なし。

### オプション B — CosyVoice（中国語に最適、オープンソース）

**3〜30 秒**の参照音声だけでクローン可能。

```bash
pip install modelscope   # API 経由なら GPU 不要
```

```bash
python3 steps/synthesize.py \
  --transcript work/transcript_zh.json \
  --out-dir    work/tts/ \
  --provider   cosyvoice \
  --ref-audio  my_recording.mp3 \
  --ref-text   "録音の中で話した内容。"
```

どちらの方法も同じ `seg_NNNN.mp3` ファイルを出力するため、`assemble.py` と `mux.py` は変更不要です。

---

## Claude Code での使用方法

`SKILL.md` をプロジェクトの `.claude/agents/` ディレクトリにコピーしてください：

```bash
cp SKILL.md /your/project/.claude/agents/video-dub.md
```

Claude Code で次のように指示するだけです：
> 「`/path/to/source.mp4` をビジネス敬語の日本語に吹き替えてください。」

Claude がスキルファイルを読み込み、パスを解決して `pipeline.py` を自動実行します。

## IBM Bob / Codex / その他の LLM ツールでの使用方法

`SKILL.md` は自己完結型の LLM 向け指示書です。お使いのツールにこのファイルを参照させてください：

- **IBM Bob**：skills/instructions ディレクトリに `video-dub.md` として追加
- **Codex / GPT-4**：`SKILL.md` の内容をシステムプロンプトまたはプロジェクト指示に含める
- **汎用**：ファイルを読み込み、シェルコマンドを実行できる LLM であれば、`SKILL.md` に従って実行できます

---

## プロジェクト構成

```
video_dub/
├── SKILL.md          LLM スキルエントリポイント
├── README.md         英語ドキュメント
├── README.ja.md      日本語ドキュメント（本ファイル）
├── requirements.txt  Python 依存パッケージ
├── install.sh        セットアップスクリプト
├── pipeline.py       全工程一括実行
└── steps/
    ├── transcribe.py Step 1：faster-whisper ASR
    ├── translate.py  Step 2：Agent 内蔵翻訳（API キー不要）
    ├── synthesize.py Step 3：edge-tts による TTS 合成
    ├── assemble.py   Step 4：セグメント単位のアセンブル（コアアルゴリズム）
    └── mux.py        Step 5：最終多重化（mux）
```

---

## ライセンス

Apache 2.0
