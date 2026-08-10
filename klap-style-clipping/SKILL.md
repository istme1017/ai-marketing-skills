---
name: klap-style-clipping
description: Turn any long-form video (podcast, webinar, talking-head, interview, stream) into short viral clips edited exactly like Klap. Use whenever the user wants to clip a video, repurpose long content into Shorts/Reels/TikToks, add Klap-style animated captions, reframe to 9:16, or asks for "clips like Klap/Opus/vidyo". Finds the viral moments, scores them, cuts them, reframes them vertical, and burns in word-by-word highlighted captions that are visually identical to Klap's default template.
allowed-tools: Read, Bash, Write, Glob, Grep
---

# klap-style-clipping

Klap takes one long video and spits out 10 short vertical clips with animated captions, and each clip looks hand-edited. This skill replicates that output end to end: same clip-selection logic, same 9:16 reframe, same caption look, same pacing. The result should be indistinguishable from a clip exported out of Klap's default template.

## Defaults

Unless told otherwise, assume the standard job: **a YouTube long-form video in, vertical clips out, posted to TikTok and YouTube Shorts.**

| Setting | Default |
|---|---|
| Source | YouTube upload (talking-head, podcast, interview) |
| Clips per source | Every moment scoring 70+, capped at 10 |
| Clip length | 25–45s (hard bounds 15–60s) |
| Output | 1080×1920, 30fps, H.264 + AAC |
| Captions | Burned in, always — see edit-spec.md |
| Destinations | TikTok and YouTube Shorts from one master render |

Two defaults worth understanding rather than just applying. **Captions are never optional** — muted autoplay is the norm on both platforms, so a clip without burned-in captions is a clip most people never hear. And **the first 1–2 seconds decide everything**: the feed is a scroll, so the clip must open on the hook word with no breath, no filler, no wind-up.

## How to use this skill

Read these in order, then run the pipeline. Do not skip the spec — the entire point is that the edit is IDENTICAL, and identical lives in the details (font weight, outline size, highlight color, pop timing).

1. [sourcing-video.md](sourcing-video.md) — getting a usable source file, plus the rights check. Read FIRST when the input is a URL: it covers the YouTube failures that stop jobs dead ("only images are available", "sign in to confirm you're not a bot", DRM), which fix applies to which, and disk-space exhaustion.
2. [clip-selection.md](clip-selection.md) — how moments get picked: what qualifies, the 0–100 virality score, hook rules, cutting discipline. Read before touching the video.
3. [edit-spec.md](edit-spec.md) — the exact visual spec: canvas, framing, caption typography, colors, highlight behavior, word-pop animation, and the ASS values that reproduce it pixel-for-pixel.
4. [distribution.md](distribution.md) — safe zones (what each app's UI covers), duration limits, the re-upload watermark penalty, and per-platform post text. Read before changing caption placement or clip length.
5. [pipeline.md](pipeline.md) — the executable pipeline: Whisper word-level transcription → cutting → 9:16 reframe → ASS caption generation → ffmpeg burn-in. Run with Bash.

Two more, for when the job is bigger than one video:

- [clip-brain.md](clip-brain.md) — the content-intelligence layer, and the real moat. Cutting is the easy half; knowing *which* moment deserves to be a clip is the hard one. Harvest TikToks that already won, trace each back to its exact moment in the source, and learn what those moments shared. Read when building the selection system rather than running a single job.
- [sources.md](sources.md) — ingesting from platforms other than YouTube. Read when the source is a **livestream VOD** (Twitch, Kick): a 6-hour stream must never be transcribed whole. Find candidate windows from viewer clips and chat-velocity spikes first, then transcribe only those.

**Uploads and streams pull in opposite directions.** An edited YouTube upload is dense — transcribe it whole and let the transcript drive selection, which is the default path above. A stream is mostly filler, so window detection has to come first. Do not apply the stream shortcut to uploads; you will skip good moments that chat never reacted to.

## The workflow, condensed

1. **Transcribe** the source video with word-level timestamps (Whisper). No transcript, no clipping — every downstream decision reads from it.
2. **Select** 3–10 self-contained moments of 15–60 seconds using clip-selection.md. Score each 0–100 and tell the user the score, exactly like Klap does.
3. **Cut** each moment with a hard hook in the first line. Re-encode at the cut (never stream-copy) so the clip starts on a frame, not a keyframe several words early.
4. **Reframe** to 1080×1920, crop centered on the speaker's face.
5. **Caption** with the Klap default template from edit-spec.md: 1–3 words on screen, ALL CAPS, white bold with black outline, active word highlighted green with a pop.
6. **Deliver** each clip as `clip-NN-<slug>.mp4` plus a one-line hook/title and its virality score. For TikTok and Shorts, the same master file posts to both — only the title/caption text differs (distribution.md).

## Harvesting TikTok to feed the brain

TikTok is not only a destination here, it is the best available training data. Winning clips in your niche are public, their engagement is public, and many were cut from long-form videos you can also obtain. That is exactly the corpus [clip-brain.md](clip-brain.md) is built on: scrape the winners, match each back to its source moment, learn what those moments had in common, and score future candidates against real evidence instead of my heuristics.

Analysing public clips to learn patterns is research. Re-uploading them is not — the corpus teaches you what to cut from your own footage.

## The one rule

Never freestyle the caption style. If the output doesn't match edit-spec.md value for value, it isn't done. "Close" is how AI clips end up looking like AI clips.
