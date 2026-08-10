---
name: klap-style-clipping
description: Turn any long-form video (podcast, webinar, talking-head, interview, stream) into short viral clips edited exactly like Klap. Use whenever the user wants to clip a video, repurpose long content into Shorts/Reels/TikToks, add Klap-style animated captions, reframe to 9:16, or asks for "clips like Klap/Opus/vidyo". Finds the viral moments, scores them, cuts them, reframes them vertical, and burns in word-by-word highlighted captions that are visually identical to Klap's default template.
allowed-tools: Read, Bash, Write, Glob, Grep
---

# klap-style-clipping

Klap takes one long video and spits out 10 short vertical clips with animated captions, and each clip looks hand-edited. This skill replicates that output end to end: same clip-selection logic, same 9:16 reframe, same caption look, same pacing. The result should be indistinguishable from a clip exported out of Klap's default template.

## How to use this skill

Read the files in this order, then run the pipeline. Do not skip the spec: the entire point is that the edit is IDENTICAL, and identical lives in the details (font weight, outline size, highlight color, pop timing).

0. [sourcing-video.md](sourcing-video.md) — getting a usable source file, and the rights check. Read this FIRST when the input is a URL rather than a local file: it covers the YouTube failures that stop jobs dead ("only images are available", "sign in to confirm you're not a bot", DRM) and which fix applies to which.
1. [clip-selection.md](clip-selection.md) — how Klap picks moments: what counts as a clippable moment, the virality score (0–100 per clip), hook rules, and clip length targets. Read this before touching the video.
2. [edit-spec.md](edit-spec.md) — the exact visual spec of the Klap edit: canvas, framing, caption typography, colors, highlight behavior, word-pop animation, emoji rules, and the ASS subtitle values that reproduce it pixel-for-pixel.
3. [clip-brain.md](clip-brain.md) — the content-intelligence layer. Cutting is the easy half; knowing *which* moment deserves to be a clip is the hard one. This replaces hand-written heuristics with evidence: harvest clips that already won, trace each back to its exact moment in the source video, and learn what those moments shared. Read it when building the selection system rather than running a single job.
4. [distribution.md](distribution.md) — publishing one master clip across YouTube Shorts, TikTok, Reels, X and Twitch: per-platform safe zones (what the app UI covers), duration limits, watermark rules, and per-platform post text. Read it before choosing caption placement or clip length.
5. [pipeline.md](pipeline.md) — the executable pipeline: Whisper word-level transcription → clip cutting → 9:16 reframe → ASS caption generation → ffmpeg burn-in. Run these steps with Bash.

## The workflow, condensed

1. **Transcribe** the source video with word-level timestamps (Whisper). No transcript, no clipping — every downstream decision reads from it.
2. **Select** 3–10 self-contained moments of 15–60 seconds using clip-selection.md. Score each 0–100 and tell the user the score, exactly like Klap does.
3. **Cut** each moment with a hard hook in the first line. Re-encode at the cut (never stream-copy) so the clip starts on a frame, not a keyframe several words early.
4. **Reframe** to 1080×1920, crop centered on the speaker's face.
5. **Caption** with the Klap default template from edit-spec.md: 1–3 words on screen, ALL CAPS, white bold with black outline, active word highlighted green with a pop.
6. **Deliver** each clip as `clip-NN-<slug>.mp4` plus a one-line hook/title and its virality score.

## The one rule

Never freestyle the caption style. If the output doesn't match edit-spec.md value for value, it isn't done. "Close" is how AI clips end up looking like AI clips.
