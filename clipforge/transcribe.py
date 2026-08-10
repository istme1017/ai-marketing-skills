"""Word-level transcription.

Everything downstream reads from this: selection needs sentence boundaries and
pause structure, captions need per-word timings. No transcript, no clipping.
"""

from __future__ import annotations

import json
import os
from typing import Any


def transcribe(video: str, model_size: str = "small", compute_type: str = "int8",
               language: str | None = None) -> list[dict[str, Any]]:
    """Return [{word, start, end}, ...] with word-level timestamps."""
    from faster_whisper import WhisperModel

    model = WhisperModel(model_size, compute_type=compute_type)
    segments, info = model.transcribe(video, word_timestamps=True, language=language)

    words: list[dict[str, Any]] = []
    for seg in segments:
        for w in seg.words or []:
            text = w.word.strip()
            if text:
                words.append({
                    "word": text,
                    "start": round(w.start, 3),
                    "end": round(w.end, 3),
                })
    return words


def load_or_transcribe(video: str, cache: str, **kw) -> list[dict[str, Any]]:
    """Transcription dominates runtime, so never do it twice for one source."""
    if os.path.exists(cache):
        with open(cache) as fh:
            return json.load(fh)
    words = transcribe(video, **kw)
    with open(cache, "w") as fh:
        json.dump(words, fh, ensure_ascii=False)
    return words


def full_text(words: list[dict[str, Any]]) -> str:
    return " ".join(w["word"] for w in words)
