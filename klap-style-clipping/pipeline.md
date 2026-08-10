# Pipeline — reproduce the Klap edit with Whisper + ffmpeg

Run this with Bash. Inputs: a source video file (or URL — download it first). Outputs: `clips/clip-NN-<slug>.mp4`, one per selected moment, fully edited per edit-spec.md.

## 0. Prerequisites

```bash
ffmpeg -version                      # required
pip install faster-whisper           # word-level transcription
# Font: Montserrat ExtraBold. If missing:
mkdir -p ~/.fonts && cd ~/.fonts
# get Montserrat-ExtraBold.ttf (Google Fonts) then:
fc-cache -f && fc-list | grep -i montserrat
```

If Montserrat truly can't be installed, use the fallback order in edit-spec.md and say so in the summary.

## 1. Transcribe with word timestamps

```python
# transcribe.py — writes words.json: [{"word": "...", "start": 1.23, "end": 1.51}, ...]
import json, sys
from faster_whisper import WhisperModel

model = WhisperModel("small", compute_type="int8")
segments, _ = model.transcribe(sys.argv[1], word_timestamps=True)
words = [{"word": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3)}
         for seg in segments for w in seg.words]
json.dump(words, open("words.json", "w"), ensure_ascii=False, indent=1)
print(f"{len(words)} words, {words[-1]['end']:.0f}s")
```

Read the full transcript text yourself afterwards — clip selection (clip-selection.md) is a judgment call you make from the words, not something a script does.

## 2. Select moments

Apply clip-selection.md to the transcript. For each chosen moment record: start word index, end word index, hook line, virality score, slug. Pad times: `start = words[i].start - 0.15`, `end = words[j].end + 0.25` (clamp to video bounds).

## 3. Cut each clip (re-encode, frame-accurate)

```bash
ffmpeg -y -ss "$START" -to "$END" -i source.mp4 \
  -c:v libx264 -preset fast -crf 18 -c:a aac -b:a 160k cut.mp4
```

Never `-c copy` here — stream copy snaps to keyframes and eats the hook.

To remove an internal silence (>1.5s between word `end` and next word `start`), cut the clip into segments around the silence and concat them (`ffmpeg -f concat`), then shift all caption timestamps after the gap left by the removed duration.

## 4. Reframe to 9:16, face-centered

Find the face center once per clip. If OpenCV is available:

```python
# facex.py — prints the face-center x in source pixels (sample 10 frames, median)
import cv2, sys, statistics
cap = cv2.VideoCapture(sys.argv[1])
det = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)); xs = []
for i in range(0, n, max(1, n // 10)):
    cap.set(cv2.CAP_PROP_POS_FRAMES, i); ok, f = cap.read()
    if not ok: continue
    faces = det.detectMultiScale(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), 1.2, 5)
    for (x, y, w, h) in faces: xs.append(x + w / 2)
print(int(statistics.median(xs)) if xs else int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) / 2))
```

Then crop and scale (crop width = source_height × 9/16, clamped so the window stays inside the frame):

```bash
ffmpeg -y -i cut.mp4 -vf \
  "crop=ih*9/16:ih:min(max(${FACE_X}-ih*9/32\,0)\,iw-ih*9/16):0,scale=1080:1920,setsar=1" \
  -c:v libx264 -preset fast -crf 18 -c:a copy framed.mp4
```

No OpenCV → center crop (`x=(iw-ih*9/16)/2`) and note it in the summary. Two-speaker split layout: crop each speaker separately and `vstack` two 1080×960 crops.

## 5. Generate the Klap captions (.ass)

One Dialogue event per WORD; each event shows the word's whole group with only the active word highlighted. This produces the exact karaoke-highlight behavior.

```python
# captions.py — words.json (already offset to clip time) -> captions.ass
import json, sys

HIGHLIGHT = r"\c&H5EC522&"   # #22C55E in ASS BGR
POP = r"\t(0,80,\fscx112\fscy112)\t(80,160,\fscx100\fscy100)"

def ts(t):
    t = max(t, 0); h = int(t // 3600); m = int(t % 3600 // 60)
    return f"{h}:{m:02d}:{t % 60:05.2f}"

words = json.load(open(sys.argv[1]))
# group into chunks of <=3 words, breaking at sentence punctuation
groups, cur = [], []
for w in words:
    cur.append(w)
    if len(cur) == 3 or w["word"].rstrip('"').endswith((".", "!", "?", ",")):
        groups.append(cur); cur = []
if cur: groups.append(cur)

ev = []
for gi, g in enumerate(groups):
    nxt = groups[gi + 1][0]["start"] if gi + 1 < len(groups) else 1e9
    for i, w in enumerate(g):
        start = w["start"]
        end = g[i + 1]["start"] if i + 1 < len(g) else min(g[-1]["end"] + 0.05, nxt)
        parts = []
        for j, x in enumerate(g):
            txt = x["word"].upper()
            parts.append(rf"{{{HIGHLIGHT}{POP}}}{txt}{{\r}}" if j == i else txt)
        ev.append(f"Dialogue: 0,{ts(start)},{ts(end)},Klap,,0,0,0,,{{\\pos(540,1340)}}{' '.join(parts)}")

open("captions.ass", "w").write("""[Script Info]
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Klap,Montserrat ExtraBold,105,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,1,8,2,5,60,60,580,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""" + "\n".join(ev) + "\n")
print(f"{len(ev)} caption events")
```

Before running it, offset the clip's words to clip-local time: `start -= CLIP_START`, `end -= CLIP_START` (and apply any silence-removal shifts). Add emojis per edit-spec.md by appending to a word's text in words.json — sparingly.

## 6. Burn in + loudness

```bash
ffmpeg -y -i framed.mp4 -vf "ass=captions.ass" \
  -af "loudnorm=I=-14:TP=-1.5:LRA=11" \
  -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p -c:a aac -b:a 160k \
  "clips/clip-01-${SLUG}.mp4"
```

## 7. Verify (every clip, no exceptions)

```bash
ffprobe -v error -select_streams v -show_entries stream=width,height,r_frame_rate "clips/clip-01-${SLUG}.mp4"
ffmpeg -y -i "clips/clip-01-${SLUG}.mp4" -ss 2 -vframes 1 check.png
```

Look at `check.png` (Read the image) and run the definition-of-done checklist in edit-spec.md. Captions off-position, wrong weight, or highlight missing → fix the .ass and re-burn. Then report per clip: filename, hook line, duration, virality score.
