"""Cutting, reframing and caption burn-in via ffmpeg."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any

from .config import RenderConfig


def run_in(cmd: list[str], cwd: str | None = None) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-6:])
        raise RuntimeError(f"ffmpeg failed ({proc.returncode}):\n{tail}")


def run(cmd: list[str]) -> None:
    run_in(cmd)


def probe(path: str) -> dict[str, Any]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,r_frame_rate",
         "-show_entries", "format=duration", "-of", "json", path],
        capture_output=True, text=True, check=True).stdout
    d = json.loads(out)
    s = d["streams"][0]
    return {"width": int(s["width"]), "height": int(s["height"]),
            "duration": float(d["format"]["duration"])}


def face_center_x(video: str, samples: int = 12) -> int | None:
    """Median horizontal face position, or None if OpenCV is unavailable."""
    try:
        import cv2
    except ImportError:
        return None

    cap = cv2.VideoCapture(video)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if total <= 0:
        cap.release()
        return None

    cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    xs: list[float] = []
    step = max(1, total // samples)
    for i in range(0, total, step):
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ok, frame = cap.read()
        if not ok:
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        for (x, _y, w, _h) in cascade.detectMultiScale(gray, 1.2, 5):
            xs.append(x + w / 2)
    cap.release()

    if not xs:
        return None
    xs.sort()
    return int(xs[len(xs) // 2])


def cut(src: str, start: float, end: float, dst: str) -> str:
    """Frame-accurate cut.

    Re-encodes deliberately: stream copy snaps to the nearest keyframe, which
    routinely eats the first word of the hook.
    """
    run(["ffmpeg", "-y", "-v", "error", "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
         "-i", src, "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
         "-c:a", "aac", "-b:a", "192k", dst])
    return dst


def reframe(src: str, dst: str, cfg: RenderConfig, focus_x: int | None = None) -> str:
    """Crop to 9:16 around the subject, then scale to the output canvas."""
    info = probe(src)
    src_w, src_h = info["width"], info["height"]
    crop_w = min(src_w, int(src_h * cfg.width / cfg.height))

    if focus_x is None:
        x = (src_w - crop_w) // 2
    else:
        x = max(0, min(focus_x - crop_w // 2, src_w - crop_w))

    vf = (f"crop={crop_w}:{src_h}:{x}:0,"
          f"scale={cfg.width}:{cfg.height}:flags=lanczos,setsar=1,fps={cfg.fps}")
    run(["ffmpeg", "-y", "-v", "error", "-i", src, "-vf", vf,
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
         "-c:a", "copy", dst])
    return dst


def burn(src: str, ass_path: str, dst: str, cfg: RenderConfig) -> str:
    """Burn captions and normalise loudness — the final render.

    The subtitle path is passed as a bare filename with ffmpeg run from its
    directory. Escaping a full path inside a filtergraph is a trap: the value
    goes through two parsers, so a Windows drive colon needs `\\:`, and an
    apostrophe cannot be escaped with `\\'` at all — it silently truncates and
    libass then fails on a filename that does not exist. Directory paths like
    `C:\\Users\\O'Brien\\clips` are ordinary, so sidestep the whole problem:
    src and dst stay absolute (plain arguments need no escaping), and only the
    slugified basename reaches the filter.
    """
    work_dir = os.path.dirname(os.path.abspath(ass_path)) or "."
    name = os.path.basename(ass_path)

    run_in(["ffmpeg", "-y", "-v", "error", "-i", os.path.abspath(src),
            "-vf", f"ass={name}",
            "-af", f"loudnorm={cfg.loudness_target}",
            "-c:v", "libx264", "-preset", cfg.preset, "-crf", str(cfg.crf),
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", cfg.audio_bitrate,
            os.path.abspath(dst)], cwd=work_dir)
    return dst


def thumbnail(src: str, dst: str, at: float = 1.0) -> str:
    run(["ffmpeg", "-y", "-v", "error", "-ss", f"{at:.2f}", "-i", src,
         "-vframes", "1", dst])
    return dst


def font_available(name: str) -> bool:
    if not shutil.which("fc-list"):
        return True                     # cannot check; let ffmpeg decide
    out = subprocess.run(["fc-list"], capture_output=True, text=True).stdout
    return name.lower() in out.lower()


def ensure_tools() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            raise RuntimeError(f"{tool} not found on PATH — install ffmpeg")


def cleanup(*paths: str) -> None:
    for p in paths:
        try:
            os.remove(p)
        except OSError:
            pass
