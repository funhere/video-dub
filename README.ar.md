[English](README.md) · [中文](README.zh.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Deutsch](README.de.md) · [Français](README.fr.md) · [Español](README.es.md) · **العربية**

---

<div dir="rtl">

# video-dub

أداة لدبلجة أي فيديو بصيغة MP4 إلى لغة أخرى، تتضمن الميزات التالية:

- **التفريغ الصوتي ASR** — faster-whisper (يعمل بالكامل بدون اتصال بالإنترنت)
- **الترجمة بالذكاء الاصطناعي** — Claude أو GPT، بأسلوب رسمي احترافي وموجز
- **تحويل النص إلى كلام TTS** — edge-tts (أكثر من 400 صوت، لا يتطلب مفتاح API)
- **مزامنة تجميد الإطار لكل مقطع** — إذا تجاوزت مدة الصوت نافذة المقطع الأصلية، يتوقف الفيديو عند آخر إطار للمقطع حتى ينتهي الكلام، مما يمنع الانجراف المتسلسل
- **ترجمة مضمّنة قابلة للتبديل** — تدفق `mov_text` يمكن تشغيله أو إيقافه في QuickTime / VLC / mpv

---

## المتطلبات

| الأداة | الإصدار | التثبيت |
|--------|---------|---------|
| Python | ≥ 3.10 | [python.org](https://www.python.org) |
| ffmpeg + ffprobe | ≥ 5.0 | `brew install ffmpeg` / `apt install ffmpeg` |
| ANTHROPIC_API_KEY | — | لترجمة Claude |
| OPENAI_API_KEY | — | لترجمة GPT (بديل) |

---

## التثبيت

</div>

```bash
git clone <رابط المستودع> video-dub
cd video-dub
bash install.sh
```

<div dir="rtl">

يقوم `install.sh` بإنشاء بيئة افتراضية `.venv/` وتثبيت جميع اعتماديات Python.

---

## البدء السريع

</div>

```bash
# تعيين مفتاح API
export ANTHROPIC_API_KEY=sk-ant-...

# تشغيل كامل الخط بأمر واحد
.venv/bin/python3 pipeline.py \
  --video  /مسار/المصدر.mp4 \
  --lang   ar \
  --voice  ar-SA-ZariyahNeural \
  --out    /مسار/المخرج_ar.mp4
```

<div dir="rtl">

يحتوي ملف MP4 الناتج على:
- التدفق 0: فيديو H.264 (يتضمن إطارات مجمّدة عند الحاجة)
- التدفق 1: صوت AAC بالعربية (ZariyahNeural بسرعة +15%)
- التدفق 2: ترجمة ناعمة بالعربية (mov_text)

---

## التنفيذ خطوة بخطوة

يمكن تشغيل كل خطوة بشكل منفصل لمراجعة النتائج الوسيطة:

</div>

```bash
# الخطوة 1 — التفريغ الصوتي (ينتج transcript_en.json)
python3 steps/transcribe.py \
  --video  source.mp4 \
  --model  medium \
  --out    work/transcript_en.json

# الخطوة 2 — الترجمة (ينتج transcript_ar.json)
python3 steps/translate.py \
  --input      work/transcript_en.json \
  --lang       ar \
  --translator claude \
  --out        work/transcript_ar.json

# الخطوة 3 — توليد الصوت TTS (ينتج work/tts_segments/seg_*.mp3)
python3 steps/synthesize.py \
  --transcript work/transcript_ar.json \
  --voice      ar-SA-ZariyahNeural \
  --rate       "+15%" \
  --out-dir    work/tts_segments/

# الخطوة 4 — التجميع (ينتج video_joined.mp4 و audio_joined.wav و subtitles.srt)
python3 steps/assemble.py \
  --video      source.mp4 \
  --transcript work/transcript_ar.json \
  --tts-dir    work/tts_segments/ \
  --out-dir    work/assembled/

# الخطوة 5 — الدمج النهائي (ينتج ملف MP4 النهائي)
python3 steps/mux.py \
  --video  work/assembled/video_joined.mp4 \
  --audio  work/assembled/audio_joined.wav \
  --srt    work/assembled/subtitles.srt \
  --lang   ar \
  --out    source_ar.mp4
```

---

<div dir="rtl">

## الاستئناف بعد الانقطاع

</div>

```bash
# تخطي التفريغ الصوتي (استخدام JSON موجود)
python3 pipeline.py --video source.mp4 \
  --transcript work/transcript_en.json \
  --lang ar --out output.mp4

# تخطي التفريغ الصوتي + الترجمة
python3 pipeline.py --video source.mp4 \
  --translated work/transcript_ar.json \
  --out output.mp4

# تخطي التفريغ الصوتي + الترجمة + TTS
python3 pipeline.py --video source.mp4 \
  --translated work/transcript_ar.json \
  --tts-dir work/tts_segments/ \
  --out output.mp4
```

---

<div dir="rtl">

## الخيارات الرئيسية

| الخيار | القيمة الافتراضية | الوصف |
|--------|------------------|-------|
| `--lang` | `ja` | رمز اللغة الهدف (BCP-47) |
| `--voice` | `ja-JP-NanamiNeural` | اسم صوت edge-tts |
| `--rate` | `+15%` | سرعة الكلام؛ +15% = وتيرة المذيع المحترف |
| `--whisper-model` | `medium` | `tiny` (سريع) ↔ `large-v3` (دقيق) |
| `--translator` | `claude` | `claude` / `openai` / `none` |
| `--style` | *(تلقائي)* | تلميح الأسلوب والمستوى لمطالبة الترجمة |
| `--crf` | `22` | جودة x264 (18=جودة عالية، 28=ملف صغير) |
| `--work-dir` | `<stem>_dub_work/` | مجلد الملفات الوسيطة |

---

## خوارزمية التجميع

```
لكل مقطع i:
  window  = segs[i+1].start − segs[i].start
  overrun = max(0, مدة TTS − window)

  ┌─────────────────────────────────────┐
  │  فيديو: مقطع أصلي (window ثانية)  │
  │         + تجميد آخر إطار           │  ← فقط إذا كان overrun > 0
  │           (overrun ثانية)           │
  └─────────────────────────────────────┘
  ┌─────────────────────────────────────┐
  │  صوت: TTS (مدة TTS ثانية)          │
  │        + صمت                        │  ← فقط إذا كان overrun = 0
  │          (window − مدة TTS ثانية)  │
  └─────────────────────────────────────┘

  رمز زمن الترجمة = الموضع التراكمي في الجدول الزمني للمخرجات
```

بما أن كل مقطع يُعالَج بشكل مستقل، لا يحدث أي انجراف متسلسل.

---

## مرجع الأصوات

نفّذ `edge-tts --list-voices` لاستعراض أكثر من 400 صوت متاح:

| اللغة | أنثى | ذكر |
|-------|------|-----|
| اليابانية | `ja-JP-NanamiNeural` | `ja-JP-KeitaNeural` |
| الصينية (ماندرين) | `zh-CN-XiaoxiaoNeural` | `zh-CN-YunxiNeural` |
| الكورية | `ko-KR-SunHiNeural` | `ko-KR-InJoonNeural` |
| الإنجليزية (أمريكية) | `en-US-JennyNeural` | `en-US-GuyNeural` |
| الإسبانية | `es-ES-ElviraNeural` | `es-ES-AlvaroNeural` |
| الفرنسية | `fr-FR-DeniseNeural` | `fr-FR-HenriNeural` |
| الألمانية | `de-DE-KatjaNeural` | `de-DE-ConradNeural` |
| العربية | `ar-SA-ZariyahNeural` | `ar-SA-HamedNeural` |

---

## الاستخدام في Claude Code

انسخ `SKILL.md` إلى مجلد `.claude/agents/` في مشروعك:

</div>

```bash
cp SKILL.md /مشروعك/.claude/agents/video-dub.md
```

<div dir="rtl">

ثم قل في Claude Code:
> «من فضلك دبلج `/مسار/المصدر.mp4` إلى العربية الفصحى بأسلوب مهني.»

سيقرأ Claude ملف المهارة ويحدد المسارات وينفّذ `pipeline.py` تلقائيًا.

---

## هيكل المشروع

</div>

```
video_dub/
├── SKILL.md          نقطة دخول المهارة للذكاء الاصطناعي
├── README.md         التوثيق بالإنجليزية
├── README.ar.md      هذا الملف
├── requirements.txt  اعتماديات Python
├── install.sh        سكريبت التثبيت
├── pipeline.py       تشغيل كامل الخط بأمر واحد
└── steps/
    ├── transcribe.py الخطوة 1: التفريغ الصوتي faster-whisper
    ├── translate.py  الخطوة 2: الترجمة بالذكاء الاصطناعي
    ├── synthesize.py الخطوة 3: توليد الصوت edge-tts
    ├── assemble.py   الخطوة 4: التجميع لكل مقطع (الخوارزمية الأساسية)
    └── mux.py        الخطوة 5: الدمج النهائي
```

<div dir="rtl">

---

## الرخصة

Apache 2.0

</div>
