"""clipforge — long-form video in, captioned vertical clips out.

    python -m clipforge SOURCE [-n 6] [-o clips/]

SOURCE is a local file or any URL yt-dlp supports.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys

from .config import Config
from . import captions, render, select, transcribe


def log(stage: str, msg: str) -> None:
    print(f"[{stage}] {msg}", flush=True)


def fetch(source: str, workdir: str) -> str:
    """Return a local path, downloading first if the source is a URL."""
    if os.path.exists(source):
        return source
    if not source.startswith(("http://", "https://")):
        raise SystemExit(f"not a file or URL: {source}")
    if not shutil.which("yt-dlp"):
        raise SystemExit("yt-dlp not installed — pip install yt-dlp")

    dst = os.path.join(workdir, "source.mp4")
    log("fetch", f"downloading {source}")
    proc = subprocess.run(
        ["yt-dlp", "-f", "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b",
         "--merge-output-format", "mp4", "-o", dst, "--no-playlist", source],
        capture_output=True, text=True)
    if proc.returncode != 0 or not os.path.exists(dst):
        tail = "\n".join(proc.stderr.strip().splitlines()[-4:])
        raise SystemExit(
            f"download failed:\n{tail}\n\n"
            "See klap-style-clipping/sourcing-video.md — 'only images available' "
            "means a missing PO token, while 'sign in to confirm you're not a bot' "
            "or HTTP 429 means the IP is blocked and no token will fix it.")
    return dst


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="clipforge", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("source", help="local video file or URL")
    p.add_argument("-o", "--out", default="clips", help="output directory")
    p.add_argument("-n", "--num", type=int, help="max clips (default 10)")
    p.add_argument("--min-score", type=int, help="score floor (default 70)")
    p.add_argument("--model", default="small", help="whisper model size")
    p.add_argument("--language", help="force language, e.g. en, es")
    p.add_argument("--moments", help="JSON of [{start,end,hook?}] to render instead of auto-selecting")
    p.add_argument("--dry-run", action="store_true", help="select and report, render nothing")
    p.add_argument("--keep-temp", action="store_true", help="keep intermediates")
    args = p.parse_args(argv)

    cfg = Config()
    cfg.whisper_model = args.model
    if args.num is not None:
        cfg.select.max_clips = args.num
    if args.min_score is not None:
        cfg.select.min_score = args.min_score

    render.ensure_tools()
    os.makedirs(args.out, exist_ok=True)
    work = os.path.join(args.out, ".work")
    os.makedirs(work, exist_ok=True)

    video = fetch(args.source, work)
    info = render.probe(video)
    log("source", f"{info['width']}x{info['height']} {info['duration']:.0f}s")

    log("transcribe", f"whisper {cfg.whisper_model} (cached per source)")
    words = transcribe.load_or_transcribe(
        video, os.path.join(work, "words.json"),
        model_size=cfg.whisper_model, compute_type=cfg.compute_type,
        language=args.language)
    log("transcribe", f"{len(words)} words")
    if not words:
        raise SystemExit("no speech found — nothing to clip")

    if args.moments:
        with open(args.moments) as fh:
            raw = json.load(fh)
        moments = [select.Moment(
            start=float(m["start"]), end=float(m["end"]),
            score=int(m.get("score", 100)), hook=m.get("hook", ""),
            text=m.get("text", ""), slug=m.get("slug") or select.slugify(m.get("hook", "clip")),
            breakdown=m.get("breakdown", {})) for m in raw]
        log("select", f"{len(moments)} moments supplied")
    else:
        moments = select.find_moments(words, cfg.select)
        log("select", f"{len(moments)} moments at score >= {cfg.select.min_score}")

    if not moments:
        log("select", "nothing scored high enough — try --min-score lower")
        return 1

    for i, m in enumerate(moments, 1):
        print(f"  {i:02d}. [{m.score:3d}] {m.start:7.1f}-{m.end:7.1f}s "
              f"({m.duration:5.1f}s)  {m.hook[:70]}")

    if args.dry_run:
        with open(os.path.join(args.out, "moments.json"), "w") as fh:
            json.dump([m.to_dict() for m in moments], fh, indent=1)
        log("done", f"dry run — moments written to {args.out}/moments.json")
        return 0

    if not render.font_available(cfg.render.font):
        log("warn", f"font '{cfg.render.font}' not found — captions will use a fallback "
                    "and will NOT match edit-spec.md")

    results = []
    for i, m in enumerate(moments, 1):
        tag = f"clip-{i:02d}-{m.slug}"
        log("render", f"{tag} ({m.duration:.1f}s)")

        raw_cut = os.path.join(work, f"{tag}-cut.mp4")
        framed = os.path.join(work, f"{tag}-framed.mp4")
        ass_path = os.path.join(work, f"{tag}.ass")
        final = os.path.join(args.out, f"{tag}.mp4")

        render.cut(video, m.start, m.end, raw_cut)
        fx = render.face_center_x(raw_cut)
        render.reframe(raw_cut, framed, cfg.render, focus_x=fx)

        clip_words = [w for w in words if w["start"] >= m.start and w["end"] <= m.end]
        captions.write_ass(captions.shift_words(clip_words, m.start), cfg.render, ass_path)
        render.burn(framed, ass_path, final, cfg.render)

        if not args.keep_temp:
            render.cleanup(raw_cut, framed)

        results.append({**m.to_dict(), "file": os.path.basename(final),
                        "face_detected": fx is not None})

    with open(os.path.join(args.out, "clips.json"), "w") as fh:
        json.dump(results, fh, indent=1)

    if not args.keep_temp:
        shutil.rmtree(work, ignore_errors=True)

    log("done", f"{len(results)} clips in {args.out}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
