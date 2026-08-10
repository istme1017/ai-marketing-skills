# clipforge

Long-form video in, captioned vertical clips out. The executable implementation of [`../klap-style-clipping/`](../klap-style-clipping/).

```bash
python -m clipforge "https://youtube.com/watch?v=..." -o clips/
python -m clipforge input.mp4 -n 6 --dry-run
```

## Install

```bash
pip install faster-whisper yt-dlp pillow
# optional, enables face-centered cropping instead of center crop:
pip install opencv-python
```

`ffmpeg` and `ffprobe` must be on PATH. Install the **Montserrat ExtraBold** font or captions fall back to another face and stop matching the spec — the program warns when it can't find it.

If the font you have is the *variable* `Montserrat[wght].ttf`, pin a static instance first. Its default axis value is 100 (Thin), so libass renders hairline text that looks nothing like the spec:

```python
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer
f = TTFont("Montserrat[wght].ttf")
inst = instancer.instantiateVariableFont(f, {"wght": 800})
inst["name"].setName("Montserrat ExtraBold", 1, 3, 1, 0x409)
inst.save("MontserratExtraBold-static.ttf")
```

## What it does

1. **Fetch** — local file, or any URL yt-dlp handles. See `sourcing-video.md` when YouTube refuses.
2. **Transcribe** — faster-whisper, word-level timestamps, cached per source so reruns are cheap.
3. **Select** — scores every sentence-aligned window 0–100 and keeps the best non-overlapping set.
4. **Cut** — re-encoded, never stream-copied; a keyframe-snapped cut eats the first word of the hook.
5. **Reframe** — 9:16 crop around the detected face, scaled to 1080×1920.
6. **Caption** — ASS karaoke: 1–3 ALL-CAPS words, active word green with a scale pop.
7. **Burn** — captions in, audio normalised to −14 LUFS.

## Options

| Flag | Meaning |
|---|---|
| `-o, --out` | output directory (default `clips`) |
| `-n, --num` | max clips (default 10) |
| `--min-score` | score floor (default 70) |
| `--model` | whisper size: tiny/base/small/medium/large |
| `--language` | force language, e.g. `en`, `es` |
| `--moments` | render supplied moments instead of auto-selecting |
| `--dry-run` | select and report, render nothing |
| `--keep-temp` | keep intermediates for debugging |

Outputs `clip-NN-<slug>.mp4` plus `clips.json` with scores, timings, hooks and score breakdowns.

## Selection is the weak part, on purpose

`select.py` implements the rubric from `clip-selection.md` as regex-and-arithmetic heuristics: hook 30, self-containment 20, emotion 20, specificity 15, pacing 15. It reliably rejects obvious junk — clips that open on "So" or "And" get marked down for depending on prior context — but it cannot tell a genuinely interesting story from a boring one. No amount of pattern matching can.

Two ways to do better, both supported:

- **Let a model pick.** Run `--dry-run`, have Claude read the transcript and choose, then feed those back with `--moments moments.json`. The program handles the mechanical work and defers the judgment.
- **Learn the weights.** [`clip-brain.md`](../klap-style-clipping/clip-brain.md) describes building a corpus of clips that actually won and deriving the scoring from evidence instead of my guesses.

## Verified behaviour

Rendered end to end on a real 91s source: 1080×1920 @ 30fps output, Montserrat ExtraBold ALL-CAPS captions, green `#22C55E` active word with a 112% pop, audio at −14 LUFS.

**Caption width is enforced against measurement, not assumption.** ASS `MarginL`/`MarginR` are ignored whenever an event uses `\pos()` — which every event here does — so margins alone constrain nothing. Measured on burned-in frames, a three-word group rendered **913px** wide and ran under the like/comment/share rail. Grouping now splits on measured width, and single words too long to split are shrunk with `\fs`. Re-measured across 80 sampled frames including the pop animation: widest line **748px at x 163–911**, inside the 150–930 safe box.

Two calibrations that matter if you change the font or size:

- libass renders a nominal ASS `Fontsize` at roughly **0.637×** what PIL reports for the same value. `_LIBASS_SCALE` in `captions.py` encodes that; re-measure it for a different font.
- The width budget must account for the pop scale and the outline, or the widest frame of the animation breaches the box even though the static line fits.
