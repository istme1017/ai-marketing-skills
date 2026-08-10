# Sources — ingesting from YouTube, Twitch, Kick and the rest

The clipper takes a URL from any supported platform and produces clips. This page covers what each platform needs on the way in. For YouTube's specific failure modes (bot checks, PO tokens, DRM) see [sourcing-video.md](sourcing-video.md).

## Supported sources

`yt-dlp` handles all of these. Verify support on your install with `yt-dlp --list-extractors | grep -i <platform>` rather than assuming — extractors get added and break constantly.

| Source | Extractor | Notes |
|---|---|---|
| YouTube video | `youtube` | Bot detection is the main obstacle. See sourcing-video.md. |
| Twitch VOD | `twitch:vod` | `twitch.tv/videos/<id>`. Long, no bot-check problem. |
| Twitch clips | `twitch:clips` | Community clips — crowd-marked moments. |
| Twitch channel clips | `twitch:videos:clips` | Lists a channel's clips in bulk. |
| Kick VOD | `kick:vod` | Same shape as Twitch. |
| Kick clips | `kick:clips` | |
| Kick live | `kick:live` | Live capture. |
| X / Twitter | `twitter` | |
| Instagram | `instagram` | Needs cookies for most content; the user extractor is currently broken. |
| Rumble, Vimeo | `Rumble`, `vimeo` | Generally straightforward. |

Basic ingestion is identical across platforms:

```bash
yt-dlp -f "bv*[height<=1080]+ba/b" --merge-output-format mp4 \
       -o "source.%(ext)s" "<URL>"
```

Platforms that gate content behind login (Instagram, some Twitch subscriber VODs, private videos) need `--cookies-from-browser <browser>` or a `--cookies` file. Only use accounts you own.

## Streams are a different problem from uploads

A YouTube upload is edited — most of it earns its place. A Twitch or Kick VOD is **4 to 8 hours of mostly nothing**, punctuated by a handful of moments that matter. Treating a stream like an upload wastes enormous time: transcribing eight hours to find six clips is hours of compute to rediscover what the audience already flagged live.

**Do not transcribe a full stream.** Find candidate windows first, transcribe only those. This is the single biggest efficiency difference in the whole system, and it makes stream clipping practical rather than theoretical.

### Signal 1 — existing platform clips (strongest)

Twitch and Kick both let viewers clip in real time. Those clips *are* the crowd voting on the best moments of that stream, already filtered by people who were watching. Pull them and you get a candidate list for free:

```bash
# every clip a channel's viewers made
yt-dlp --flat-playlist -J "https://www.twitch.tv/<channel>/clips" > clips.json
```

To place a clip back in its source VOD, the Twitch Helix `Get Clips` endpoint returns a **`vod_offset`** field (seconds into the VOD) alongside `view_count` and `created_at`. `yt-dlp` does *not* surface that field, so call the API directly for it. It can be null on older clips — when it is, fall back to transcript matching from [clip-brain.md](clip-brain.md), which recovers the timestamp from the audio.

View counts on those clips are a ready-made popularity label. Feed them straight into the clip brain.

### Signal 2 — chat velocity

Chat message rate is a live excitement meter. Spikes mark hype, laughter, drama and big plays — the exact moments worth clipping. Pull the chat replay, bucket messages per second, and take the peaks:

```python
# chat replay -> candidate windows
from collections import Counter

def candidates(messages, bucket_s=5, top_n=25, pad_s=20):
    """messages: [{"offset_s": float, ...}] from the VOD chat replay."""
    hist = Counter(int(m["offset_s"] // bucket_s) for m in messages)
    if not hist:
        return []
    baseline = sorted(hist.values())[len(hist) // 2]          # median rate
    spikes = [(b, c) for b, c in hist.items() if c >= max(3 * baseline, 5)]
    spikes.sort(key=lambda x: -x[1])

    out = []
    for b, c in spikes[:top_n]:
        t = b * bucket_s
        start = max(0, t - pad_s)                             # context precedes the reaction
        out.append({"start": start, "end": t + pad_s, "intensity": round(c / baseline, 2)})
    return merge_overlaps(out)

def merge_overlaps(ws):
    ws = sorted(ws, key=lambda w: w["start"]); out = []
    for w in ws:
        if out and w["start"] <= out[-1]["end"]:
            out[-1]["end"] = max(out[-1]["end"], w["end"])
            out[-1]["intensity"] = max(out[-1]["intensity"], w["intensity"])
        else:
            out.append(dict(w))
    return out
```

Two details that decide whether this works:

- **Pad backwards.** Chat reacts *after* the thing happens, typically 2–10 seconds late. The clip must start before the spike or you capture the reaction and miss the cause. The 20s lead above is a starting point; tune it per streamer.
- **Use a relative threshold.** A 10k-viewer channel and a 200-viewer channel have wildly different baseline rates. Comparing against that stream's own median, as above, travels between channels; a fixed message count does not.

Chat emotes are a bonus signal — bursts of laughter emotes, clip-worthy reactions, and channel-specific hype emotes are stronger indicators than raw volume when you can parse them.

**Verified on a simulated 1-hour stream** (3,000 background messages plus three planted hype spikes): all three spikes were recovered at 26–28× baseline intensity, windows correctly opened ~30s *before* each spike, and total audio for transcription dropped to 205s — 5.7% of the stream.

The run also produced one borderline window at 3.0× — the `3 * baseline` floor catches ordinary chatter fluctuation. Real spikes were an order of magnitude above it, so **use the `intensity` score to filter rather than trusting the threshold**: keep windows above ~5×, and treat 3–5× as maybes worth a look only when you need more candidates. Raising the floor instead of filtering afterwards risks dropping genuine but quieter moments in a small channel.

### Signal 3 — audio energy (fallback)

No chat replay and no clips? Fall back to the audio. Loudness spikes and laughter track excitement reasonably well:

```bash
ffmpeg -i source.mp4 -af "loudnorm=print_format=json,astats=metadata=1:reset=30" -f null - 2>&1
```

Weaker than crowd signal — a loud moment is not necessarily a good one — but far better than transcribing blind.

## The stream pipeline

1. Download the VOD (`twitch:vod` / `kick:vod`).
2. Build candidate windows from clips + chat velocity, merged and deduplicated.
3. Transcribe **only those windows**, with an extra 30s of padding on each side, using the Whisper step from [pipeline.md](pipeline.md).
4. Apply [clip-selection.md](clip-selection.md) inside each window to find exact in/out points on word boundaries.
5. Render per [edit-spec.md](edit-spec.md), publish per [distribution.md](distribution.md).

Twenty windows of 40 seconds is about 13 minutes of audio instead of eight hours — roughly a 35× reduction, and the candidates are better than anything a blind transcript scan would surface.

## Streamer clips need different edits

Two adjustments the upload-oriented spec does not make:

- **The webcam is not always the subject.** Gameplay, the guest, or a shared screen may carry the moment. Face-centered crop is the wrong default here; pick the crop per clip, and consider the split layout from edit-spec.md when both the cam and the screen matter.
- **Streams have long silences.** Silence removal (pipeline.md step 3) matters far more than on edited uploads — expect to cut significantly more dead air.
