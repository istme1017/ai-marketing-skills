# The clip brain — learning which moments win instead of guessing

Cutting video is the easy half and it is already solved: ffmpeg, Remotion, and the pipeline in [pipeline.md](pipeline.md) will happily render a thousand clips. The hard half is knowing **which 40 seconds of a two-hour video deserve to be a clip at all.** A model reading a transcript cold has no content intelligence — it guesses, and the guesses are why AI clips underperform hand-picked ones.

[clip-selection.md](clip-selection.md) encodes my heuristics for that judgment. Heuristics are a starting point, not the answer. This page replaces them with evidence: harvest clips that already won, trace each one back to the exact moment in its source video, and learn what those moments had in common. That corpus is the clip brain, and it is the real moat — the edit is commodity, the selection is not.

## The loop

```
short-form accounts ──scrape──▶ clips + engagement metrics
                                        │
long-form sources ───scrape──▶ transcripts + timestamps
                                        │
                                   MATCH clip ⇄ source moment
                                        │
                                   ANALYZE what wins
                                        │
                                   SCORE new candidates
                                        │
                                   RENDER ──▶ publish ──▶ metrics ──┐
                                        ▲                           │
                                        └───────── feedback ────────┘
```

## Stage 1 — Harvest the winners

Pick 20–50 accounts in your niche that clip long-form content well (podcast clip accounts are ideal: high volume, one obvious source, public metrics). Scrape every clip with a scraper such as Apify, and pull **everything**, not just view counts:

`platform, account, clip_url, posted_at, duration_s, views, likes, comments, shares, saves, caption_text, hashtags, thumbnail_url`

Volume matters. A few hundred clips shows you nothing; a few thousand starts producing signal that survives scrutiny.

**Normalize before comparing anything.** Raw views measure account size and luck, not clip quality. A 300k-view clip on a 4M-follower account is a *flop*; 80k on a 200k account is a hit. Store a relative score — the clip's views divided by that account's median views in the same 90-day window — and rank on that. Skipping this step means you learn which accounts are big, which you already knew.

## Stage 2 — Trace each clip back to its source

This is the step that creates the data nobody else has, and the technically interesting one.

1. Scrape the long-form source (the full podcast episode) with its transcript and timestamps.
2. Transcribe each short clip (Whisper, word-level — same as pipeline.md).
3. **Align the clip transcript against the long-form transcript** to recover the exact `start`/`end` in the source.

Matching by exact string fails — the two transcriptions of the same audio disagree. Use fuzzy alignment: normalize both sides, slide the clip's word sequence over the source, and take the best window above a threshold (~0.75).

**Compare at the character level, not the word level.** This is the detail that decides whether the stage works at all. Word-level comparison treats `tell` vs `tells` and `nich` vs `niche` as total mismatches, so two ASR slips in a six-word window drop the ratio to 0.67 and the match is rejected — precisely the case the fuzzy matcher exists to catch. Joining the window into a string first scores that same pair at 0.97.

```python
# locate a clip's word sequence inside the source transcript
from difflib import SequenceMatcher

def find_source_window(clip_words, src_words, thresh=0.75):
    norm = lambda ws: [w.lower().strip('.,!?"\'') for w in ws]
    c = norm(clip_words)
    s = norm([w["word"] for w in src_words])
    cj, n, best = " ".join(c), len(c), (0.0, None)

    for i in range(0, len(s) - n + 1):
        r = SequenceMatcher(None, cj, " ".join(s[i:i + n])).ratio()   # char-level
        if r > best[0]:
            best = (r, i)

    if best[0] < thresh:
        return None                      # unmatched — do not force it
    i = best[1]
    return {"start": src_words[i]["start"],
            "end":   src_words[i + n - 1]["end"],
            "confidence": round(best[0], 3)}
```

Verified behavior: an exact quote scores 1.0; `everyone tell you to nich down` against `everyone tells you to niche down` scores 0.968; heavier corruption still matches at 0.87 with slight window drift; unrelated text correctly returns `None`.

Match on a distinctive 8–15 word span from the clip's middle rather than the whole clip — long sequences make the scan quadratic and slow, and clip edges are where ASR is least reliable. Always store `confidence` and review anything under ~0.85 before trusting its timestamps.

Now every winning clip has a row saying: *this exact 43-second window of this episode became a clip that did 4.2× the account's median.* Repeat a few thousand times and you have a labeled dataset of what a clippable moment looks like.

## Stage 3 — Analyze what actually wins

With clips joined to their source moments, ask the questions the corpus can answer:

- **Hooks.** Cluster the opening sentence by pattern (contrarian claim, number, question, story cold-open, name-drop). Which patterns land, in this niche, at what effect size?
- **Length.** Where does the performance curve actually peak? It moves by platform and niche — do not assume it is 60s because someone said so.
- **Position in source.** Do winners cluster in the first twenty minutes, or after the guest warms up?
- **Speaker.** Host or guest? Monologue or exchange?
- **Content type.** Story, tactic, hot take, stat, confession.
- **Delivery.** Words per minute, pause density, laughter, volume spikes — computable from the audio and word timings you already have.

Two failure modes to design against, because both produce confident nonsense:

- **Survivorship bias.** You only see moments someone chose to clip. You cannot conclude those were the *best* moments — only that they beat other published clips. Keep the claim honest: this is about what wins *given* it was published.
- **Spurious patterns.** With enough dimensions, something always correlates. Require a pattern to hold across multiple accounts and to survive a holdout split before you trust it.

## Stage 4 — Score new candidates against learned patterns

Replace the fixed weights in clip-selection.md with weights the corpus earned. Keep the same 0–100 output so everything downstream still works, but derive the factors from evidence and record which patterns fired:

```json
{
  "start": 1284.5, "end": 1327.2,
  "score": 87,
  "matched_patterns": ["contrarian_open", "specific_number", "guest_story"],
  "nearest_neighbors": [
    {"clip_url": "...", "relative_performance": 4.2, "similarity": 0.83}
  ],
  "hook_line": "Everyone tells you to niche down. That's backwards."
}
```

Surfacing the neighbors matters as much as the score: "this resembles three clips that did 4× on comparable accounts" is a claim you can check, while a bare 87 is a number you have to take on faith.

## Stage 5 — Close the loop

Publish, wait 7 and 30 days, pull your own metrics back into the same table, normalized the same way. Your own results outrank scraped ones — they are the only data matched to your audience, your face, and your niche. After a few hundred of your own clips, the brain is tuned to you rather than to podcast accounts in general.

## Stack

Nothing here is exotic; the value is in the corpus, not the components.

| Job | Tool |
|---|---|
| Scrape short-form + metrics | Apify (or any scraper that returns full engagement data) |
| Transcribe | Whisper / faster-whisper, word-level |
| Match, analyze, score | Claude, driven by this skill |
| Store | Supabase (Postgres) |
| Render | ffmpeg per pipeline.md, or Remotion for programmatic React edits |
| Idea backlog | Notion, or whatever you already use |

## Schema to start from

```sql
create table clips (
  id bigserial primary key,
  platform text, account text, clip_url text unique,
  posted_at timestamptz, duration_s numeric,
  views bigint, likes bigint, comments bigint, shares bigint, saves bigint,
  relative_performance numeric,          -- views / account 90d median
  caption_text text, transcript text,
  source_video_id text,                  -- null until matched
  source_start_s numeric, source_end_s numeric, match_confidence numeric,
  hook_pattern text, content_type text, speaker text
);

create table sources (
  id text primary key,                   -- platform video id
  title text, channel text, duration_s numeric,
  transcript jsonb                       -- word-level: [{word,start,end}]
);
```

`relative_performance` is the label everything trains against. Compute it once at ingest and index it.

## Sequencing

Do not build all five stages before shipping anything. Stage 1 plus Stage 2 on a single niche and ~500 clips already beats hand-written heuristics, and it tells you whether the matching works before you invest in analysis. Add stages 3–5 once the corpus is real.

## Rights

Scraping public metrics to learn patterns is analysis. Re-uploading other people's clips is not — the corpus teaches you what to cut from **your own** footage. Keep that line clean.
