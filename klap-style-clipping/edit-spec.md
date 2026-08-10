# Edit spec — the Klap look, value for value

This is the visual contract. Every clip must match ALL of these values. If a render deviates (thinner outline, lowercase words, captions at the bottom, whole sentences on screen), it reads instantly as "not Klap" — redo it.

## Canvas & framing

- **Output:** 1080×1920 (9:16), H.264, 30 fps (keep source fps if 24/25/60), AAC audio 128k+, `yuv420p`.
- **Reframe:** crop the source to 9:16 — never letterbox, never blur-pad. Crop window is centered on the active speaker's face; face sits at roughly **40% from the top** of the frame (eyes around y≈700 on the 1920 canvas).
- **Single speaker:** one static crop per clip is fine if they don't move; re-center with a hard cut (not a pan) if they shift.
- **Two speakers on screen:** split layout — speaker A in the top half (1080×960), speaker B in the bottom half, each face-centered. Switch to full-frame single crop when only one person talks for the whole clip.
- **Zero decoration:** no borders, no watermark, no progress bar, no background music added. Klap's default template is clean video + captions only.

## Caption typography (the core of the look)

- **Font:** Montserrat **ExtraBold / Black** (weight 800–900). Acceptable fallbacks in order: Archivo Black, Anton, system sans at weight 900. Regular/SemiBold is an automatic fail — the look IS the heavy weight.
- **Case:** ALL CAPS, always. Transform every word.
- **Size:** ~105px on the 1920-tall canvas (≈5.5% of frame height). One line, never two.
- **Words on screen:** **1–3 words at a time** (group the transcript into chunks of ≤3 words that never cross a sentence boundary; a long word can stand alone). Never full sentences.
- **Position:** horizontally centered, baseline block centered at **y ≈ 1340** (≈70% down the frame) — the "lower-middle" zone. NOT bottom-pinned: it must clear TikTok/Reels UI and sit under the speaker's chest, not on their face.
- **Base color:** pure white `#FFFFFF`.
- **Outline:** black `#000000`, thick — ~8px at this scale.
- **Shadow:** soft black drop shadow, ~2px offset, ~60% opacity, straight down-right.
- **Letter spacing:** default (0). No italics, no underline.

## The highlight (what makes it "Klap")

- Captions are **word-by-word karaoke**: the whole 1–3 word group is on screen in white, and the word currently being spoken is recolored.
- **Highlight color:** Klap-green **`#22C55E`** (default template). If the user asks for the yellow or purple Klap template, use `#FDE047` / `#A855F7` — same everything else.
- **Only the fill changes.** Outline stays black, size of non-active words stays fixed.
- **Word pop:** when a word becomes active it scales **100% → 112% → 100%** over ~160ms (80ms up, 80ms back). Only the active word pops.
- Timing comes from Whisper **word-level** timestamps. A word is highlighted from its start time to the next word's start time. The group stays on screen from its first word's start to its last word's end (+0.05s).

## Emojis

- Sparse: **at most one emoji per clip-worth of captions per ~10 seconds**, only when a word maps obviously (money → 💰, growth → 📈, fire take → 🔥, mind-blown → 🤯, laughing → 😂).
- The emoji is appended after the word in the same caption group, same size as the text. Never emoji-only captions. When in doubt, no emoji — Klap under-uses them.

## Audio & pacing

- Keep original voice audio untouched (no music bed in the default template).
- Loudness-normalize to **-14 LUFS** (`loudnorm=I=-14:TP=-1.5:LRA=11`).
- Dead air >1.5s inside a clip is cut (see clip-selection.md). Cuts are hard cuts.

## ASS reference values (what the pipeline generates)

The pipeline burns captions from an `.ass` file. These are the canonical values — pipeline.md consumes them:

```
PlayResX: 1080, PlayResY: 1920
Style: Klap,Montserrat ExtraBold,105,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,1,8,2,5,150,150,580,1
Highlight fill override: \c&H5EC522&   (ASS is BGR: #22C55E → &H5EC522&)
Position override per event: \pos(540,1340)
Active-word pop: \t(0,80,\fscx112\fscy112)\t(80,160,\fscx100\fscy100)
One Dialogue event per active word, containing the full 1–3 word group
with only the active word carrying the highlight + pop overrides.
```

Alignment 5 (middle-center) + `\pos(540,1340)` keeps the block fixed so words don't jitter as the highlight moves.

**Margins are 150, not 60, and that is deliberate.** Every platform stacks its like/comment/share icons in a right rail from about x = 930 to the edge, and that rail runs straight through the caption's vertical band. At 60px margins a wide three-word group can span to x ≈ 1020 and slide under the icons. Margins of 150 cap the text box at 780px wide (x 150–930), which clears the rail on TikTok, Shorts, and Reels.

780px fits roughly 12 ExtraBold characters at 105px. When a three-word group is wider than that, drop it to two words rather than letting it wrap or overflow — `WrapStyle: 2` does not wrap, so an over-wide line runs off the safe area silently. Vertically the block spans y 1280–1400, which clears the tightest bottom overlay (Reels, from y ≈ 1500) by 100px. See [distribution.md](distribution.md) for the full safe-zone table.

## Definition of done (check every clip)

1. 1080×1920, no bars, face at ~40% height.
2. Captions: ≤3 ALL-CAPS words, Montserrat ExtraBold ~105px, white with thick black outline, centered at ~70% height.
3. Active word is green #22C55E and pops ~112% for ~160ms, in sync with the voice (drift < 100ms).
4. Clip opens on the hook word, ends on the landing word, no dead air >1.5s inside.
5. Audio at -14 LUFS, no added music.
