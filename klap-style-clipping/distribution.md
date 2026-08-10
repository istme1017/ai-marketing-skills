# Distribution — one master clip, many platforms

You are cutting once and posting to YouTube Shorts, TikTok, Instagram Reels, X, Twitch and whatever comes next. Render **one 1080×1920 master** and adapt around it. Re-rendering per platform multiplies disk and time for differences that mostly are not visual.

But "post the same file everywhere" is wrong in three specific ways, and each one costs reach.

## 1. Safe zones — the one that actually breaks clips

Every app paints its own UI over your video. Anything you place under that chrome is invisible to the viewer, and captions are the usual casualty.

Approximate overlay zones on a 1080×1920 canvas:

| Platform | Top | Bottom | Right rail |
|---|---|---|---|
| TikTok | ~0–200 | ~1600–1920 (caption, username, music) | ~930–1080 (like/comment/share) |
| YouTube Shorts | ~0–150 | ~1650–1920 (title, channel, actions) | ~940–1080 |
| Instagram Reels | ~0–180 | ~1500–1920 (caption, audio, profile) | ~930–1080 |
| X / Twitter | ~0–150 | ~1700–1920 | minimal |

Reels is the tightest at the bottom — design to it and you clear all of them.

**The rule that satisfies every platform at once: keep captions and any burned-in text between 55% and 75% of frame height (y ≈ 1050–1440), horizontally centered, never wider than x 100–980.**

The caption baseline in [edit-spec.md](edit-spec.md) sits at y ≈ 1340, inside that band on purpose. If you move it, move it *up*, never down. Faces should also stay above y ≈ 1500 so the subject is not buried under the caption bar.

These pixel values shift with app updates. Treat the percentage rule as the contract and the table as a snapshot — verify on a real device once per quarter, and after any major app redesign.

## 2. Duration limits

| Platform | Hard limit | What actually performs |
|---|---|---|
| YouTube Shorts | 3 min | 20–60s |
| TikTok | 10 min | 20–60s |
| Instagram Reels | 3 min | 15–45s |
| X / Twitter | ~2:20 (free tier) | 30–60s |
| LinkedIn | 10 min | 30–90s |

A 15–60s master clears every one of these. That is why [clip-selection.md](clip-selection.md) targets that range — it is a distribution constraint, not an aesthetic preference. Go past 90s and you start losing platforms and retention together.

## 3. Never post a file carrying another platform's watermark

TikTok demotes videos with visible TikTok watermarks re-uploaded elsewhere, and every platform does some version of this. It is the single most common self-inflicted reach problem.

Always publish from your **own master render**, never from a download of your own post on another app. If you must re-download, the watermark is baked into the pixels and cropping it out damages the frame — re-render from source instead.

Related: strip identifying metadata that ties the file to another platform, and give each upload a fresh filename. Cheap to do, occasionally matters.

```bash
ffmpeg -i master.mp4 -map_metadata -1 -c copy clip-yt-01.mp4
```

## Per-platform text, not per-platform video

The video is the same. The words around it are not, and this is where most of the per-platform effort should go:

- **YouTube Shorts** — title carries the click. Front-load the hook, under ~60 characters. Hashtags matter little.
- **TikTok** — the on-screen caption in the first second matters more than the description. 3–5 relevant hashtags, not 30.
- **Instagram Reels** — first line of the caption is the hook; the rest is collapsed. Original audio helps reach.
- **X** — the post text does the work; treat the video as the payload. No hashtags.
- **LinkedIn** — a short framing sentence, professional context, no hashtag spam.

Generate these per clip from the hook line the selection step already produced. One clip, five posts, five different framings.

## Twitch as a source

Twitch is usually where footage *comes from* rather than where clips go. yt-dlp handles Twitch VODs and clips with the same interface as YouTube, and it does not carry YouTube's bot-detection problem, so downloads are typically straightforward:

```bash
yt-dlp -f "bv*+ba/b" -o "source.%(ext)s" "https://www.twitch.tv/videos/VIDEO_ID"
```

Long streams are mostly dead air. Do not transcribe eight hours blind — pull the chat replay or the existing Twitch clips first to find the spikes, then transcribe only around those windows. It is far cheaper and the crowd has already marked the good moments for you.

## Output naming

Make files self-describing so a batch across platforms stays sortable:

```
clip-03-niche-down-is-backwards--yt.mp4
clip-03-niche-down-is-backwards--tt.mp4
```

Same clip number, same slug, platform suffix. When something performs, you can trace it back to the source moment in seconds — and that traceability is what feeds [clip-brain.md](clip-brain.md).

## Posting cadence

Do not dump ten clips from one source on one day to one account. Space them, and lead with your highest-scoring clip — the first post teaches the algorithm what the account is about. Hold the weakest clips back entirely; publishing filler to hit a number trains the wrong signal and pollutes your own performance data.
