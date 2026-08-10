"""One clipping job, shared by the CLI and the web UI.

Both entry points call run_job(); progress arrives through a callback so the
web UI can stream it and the CLI can print it.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any, Callable

from .config import Config
from . import captions, render, select, transcribe

Progress = Callable[[str, str], None]


def _noop(stage: str, msg: str) -> None:
    pass


@dataclass
class JobOptions:
    out_dir: str = "clips"
    num_clips: int | None = None
    min_score: int | None = None
    model: str = "small"
    language: str | None = None
    moments_file: str | None = None
    keep_temp: bool = False
    burn_captions: bool = True
    dry_run: bool = False


@dataclass
class JobResult:
    clips: list[dict[str, Any]] = field(default_factory=list)
    moments: list[Any] = field(default_factory=list)
    source_info: dict[str, Any] = field(default_factory=dict)
    out_dir: str = ""


class JobError(RuntimeError):
    """Failure with a message meant for a human, not a stack trace."""


def fetch(source: str, workdir: str, on: Progress) -> str:
    if os.path.exists(source):
        return source
    if not source.startswith(("http://", "https://")):
        raise JobError(f"Not a file or URL: {source}")
    if not shutil.which("yt-dlp"):
        raise JobError("yt-dlp is not installed. Run: pip install -U yt-dlp")

    dst = os.path.join(workdir, "source.mp4")
    on("fetch", f"Downloading {source}")
    proc = subprocess.run(
        ["yt-dlp", "-f",
         "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b",
         "--merge-output-format", "mp4", "-o", dst, "--no-playlist", source],
        capture_output=True, text=True)

    if proc.returncode != 0 or not os.path.exists(dst):
        err = proc.stderr or ""
        if "only images are available" in err.lower():
            raise JobError(
                "YouTube returned no video streams (only thumbnails). This means a "
                "missing PO token — run setup-ytdlp-potoken.sh, then retry.")
        if "not a bot" in err.lower() or "429" in err:
            raise JobError(
                "YouTube is blocking this machine's IP address. A PO token will not "
                "fix this. Try again later, or pass browser cookies to yt-dlp.")
        if "no space left" in err.lower():
            raise JobError("Disk full. Free space and retry.")
        tail = "\n".join(err.strip().splitlines()[-3:])
        raise JobError(f"Download failed:\n{tail}")
    return dst


def run_job(source: str, opts: JobOptions, on: Progress | None = None) -> JobResult:
    on = on or _noop
    cfg = Config()
    cfg.whisper_model = opts.model
    if opts.num_clips is not None:
        cfg.select.max_clips = opts.num_clips
    if opts.min_score is not None:
        cfg.select.min_score = opts.min_score

    render.ensure_tools()
    os.makedirs(opts.out_dir, exist_ok=True)
    work = os.path.join(opts.out_dir, ".work")
    os.makedirs(work, exist_ok=True)

    video = fetch(source, work, on)
    info = render.probe(video)
    on("source", f"{info['width']}x{info['height']}, {info['duration']:.0f}s")

    on("transcribe", f"Transcribing with whisper '{cfg.whisper_model}' "
                     f"(~{max(1, int(info['duration'] / 60))} min of audio)")
    words = transcribe.load_or_transcribe(
        video, os.path.join(work, "words.json"),
        model_size=cfg.whisper_model, compute_type=cfg.compute_type,
        language=opts.language)
    if not words:
        raise JobError("No speech detected — nothing to clip.")
    on("transcribe", f"{len(words)} words")

    if opts.moments_file:
        with open(opts.moments_file) as fh:
            raw = json.load(fh)
        moments = [select.Moment(
            start=float(m["start"]), end=float(m["end"]),
            score=int(m.get("score", 100)), hook=m.get("hook", ""),
            text=m.get("text", ""),
            slug=m.get("slug") or select.slugify(m.get("hook", "clip")),
            breakdown=m.get("breakdown", {})) for m in raw]
        on("select", f"{len(moments)} moments supplied")
    else:
        moments = select.find_moments(words, cfg.select)
        on("select", f"{len(moments)} moments scoring >= {cfg.select.min_score}")

    if not moments:
        raise JobError(
            f"No moment scored {cfg.select.min_score} or higher. Lower the "
            "minimum score, or the source may not contain self-contained moments.")

    if opts.dry_run:
        with open(os.path.join(opts.out_dir, "moments.json"), "w") as fh:
            json.dump([m.to_dict() for m in moments], fh, indent=1)
        on("done", f"dry run — {len(moments)} moments written to moments.json")
        return JobResult(moments=moments, source_info=info, out_dir=opts.out_dir)

    if opts.burn_captions and not render.font_available(cfg.render.font):
        on("warn", f"Font '{cfg.render.font}' not found — captions will use a "
                   "fallback and will not match the spec.")

    results: list[dict[str, Any]] = []
    for i, m in enumerate(moments, 1):
        tag = f"clip-{i:02d}-{m.slug}"
        on("render", f"[{i}/{len(moments)}] {tag} — {m.duration:.0f}s, score {m.score}")

        raw_cut = os.path.join(work, f"{tag}-cut.mp4")
        framed = os.path.join(work, f"{tag}-framed.mp4")
        final = os.path.join(opts.out_dir, f"{tag}.mp4")

        render.cut(video, m.start, m.end, raw_cut)
        focus = render.face_center_x(raw_cut)
        render.reframe(raw_cut, framed, cfg.render, focus_x=focus)

        if opts.burn_captions:
            ass_path = os.path.join(work, f"{tag}.ass")
            clip_words = [w for w in words
                          if w["start"] >= m.start and w["end"] <= m.end]
            captions.write_ass(
                captions.shift_words(clip_words, m.start), cfg.render, ass_path)
            render.burn(framed, ass_path, final, cfg.render)
        else:
            shutil.move(framed, final)

        if not opts.keep_temp:
            render.cleanup(raw_cut, framed)

        results.append({**m.to_dict(), "file": os.path.basename(final),
                        "face_detected": focus is not None})

    with open(os.path.join(opts.out_dir, "clips.json"), "w") as fh:
        json.dump(results, fh, indent=1)

    if not opts.keep_temp:
        shutil.rmtree(work, ignore_errors=True)

    on("done", f"{len(results)} clips ready")
    return JobResult(clips=results, source_info=info, out_dir=opts.out_dir)
