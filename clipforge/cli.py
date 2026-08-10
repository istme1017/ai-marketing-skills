"""clipforge — long-form video in, captioned vertical clips out.

    python -m clipforge SOURCE [-n 6] [-o clips/]

SOURCE is a local file or any URL yt-dlp supports.
For the web UI instead: python -m clipforge.web
"""

from __future__ import annotations

import argparse
import sys

from .job import JobError, JobOptions, run_job


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="clipforge", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("source", help="local video file or URL")
    p.add_argument("-o", "--out", default="clips", help="output directory")
    p.add_argument("-n", "--num", type=int, help="max clips (default 10)")
    p.add_argument("--min-score", type=int, help="score floor (default 70)")
    p.add_argument("--model", default="small", help="whisper model size")
    p.add_argument("--language", help="force language, e.g. en, es")
    p.add_argument("--moments",
                   help="JSON of [{start,end,hook?}] to render instead of auto-selecting")
    p.add_argument("--no-captions", action="store_true",
                   help="skip burned-in captions (not recommended — muted autoplay)")
    p.add_argument("--dry-run", action="store_true",
                   help="select and report, render nothing")
    p.add_argument("--keep-temp", action="store_true", help="keep intermediates")
    args = p.parse_args(argv)

    opts = JobOptions(
        out_dir=args.out, num_clips=args.num, min_score=args.min_score,
        model=args.model, language=args.language, moments_file=args.moments,
        keep_temp=args.keep_temp, burn_captions=not args.no_captions,
        dry_run=args.dry_run,
    )

    def on(stage: str, msg: str) -> None:
        print(f"[{stage}] {msg}", flush=True)

    try:
        result = run_job(args.source, opts, on)
    except JobError as exc:
        print(f"\nerror: {exc}", file=sys.stderr)
        return 1

    for i, m in enumerate(result.moments or result.clips, 1):
        d = m if isinstance(m, dict) else m.to_dict()
        print(f"  {i:02d}. [{d['score']:3d}] {d['start']:7.1f}-{d['end']:7.1f}s "
              f"({d['duration']:5.1f}s)  {d['hook'][:70]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
