"""Moment selection.

Implements the 0-100 rubric from klap-style-clipping/clip-selection.md as
executable heuristics: hook 30, self-containment 20, emotion 20,
specificity 15, pacing 15.

These are heuristics, and heuristics are a floor rather than an answer. The
honest upgrade path is clip-brain.md — learn the weights from clips that
actually won. Until that corpus exists, this is a defensible default, and
`--moments` lets a better judge (a human, or Claude reading the transcript)
override it entirely.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Any

from .config import SelectConfig

SENTENCE_END = (".", "!", "?")

# Openers that promise a payoff.
HOOK_PATTERNS = [
    r"^(nobody|no one|everyone|everybody)\b",
    r"^(here'?s|this is) (why|how|what|the)\b",
    r"^(the (biggest|worst|best|number one|#1|hardest|only))\b",
    r"^(most people|most of you|they don'?t|they never)\b",
    r"^(if you|when you|you (need|have|should|can))\b",
    r"^(i (was|used to|never|almost|once))\b",
    r"^(stop|never|always|forget|listen)\b",
    r"^(what|why|how|when) .*\?$",
    r"\b(mistake|secret|truth|myth|wrong|backwards)\b",
]

# Discourse markers that mean the sentence depends on earlier context.
DANGLING = [
    r"^(so|and|but|because|then|also|anyway|however|which|that'?s why)\b",
    r"^(he|she|they|it|this|that|those|these)\b",
]

EMOTION = [
    r"\b(insane|crazy|wild|shocking|unbelievable|incredible|amazing|terrible|awful)\b",
    r"\b(love|hate|scared|afraid|angry|excited|obsessed)\b",
    r"\b(never|ever|literally|actually|honestly|seriously)\b",
    r"!",
    r"\b(laugh|laughing|funny|hilarious)\b",
]

FILLER = {"um", "uh", "like", "yeah", "okay", "ok", "right", "mean", "know", "so"}


@dataclass
class Moment:
    start: float
    end: float
    score: int
    hook: str
    text: str
    slug: str
    breakdown: dict[str, int]

    @property
    def duration(self) -> float:
        return round(self.end - self.start, 2)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["duration"] = self.duration
        return d


def build_sentences(words: list[dict]) -> list[dict]:
    """Group words into sentences, keeping index ranges into the word list."""
    sentences, cur, start_i = [], [], 0
    for i, w in enumerate(words):
        cur.append(w)
        if w["word"].rstrip('"\'').endswith(SENTENCE_END):
            sentences.append({
                "text": " ".join(x["word"] for x in cur),
                "start": cur[0]["start"], "end": cur[-1]["end"],
                "i0": start_i, "i1": i,
            })
            cur, start_i = [], i + 1
    if cur:
        sentences.append({
            "text": " ".join(x["word"] for x in cur),
            "start": cur[0]["start"], "end": cur[-1]["end"],
            "i0": start_i, "i1": len(words) - 1,
        })
    return sentences


def _matches(patterns: list[str], text: str) -> int:
    t = text.lower().strip()
    return sum(1 for p in patterns if re.search(p, t))


def score_moment(sents: list[dict], words: list[dict], cfg: SelectConfig) -> tuple[int, dict]:
    text = " ".join(s["text"] for s in sents)
    first = sents[0]["text"]
    dur = sents[-1]["end"] - sents[0]["start"]
    n_words = sum(s["i1"] - s["i0"] + 1 for s in sents)

    # Hook (30) — does the opening line earn the next three seconds?
    hook = min(30, 10 + 10 * _matches(HOOK_PATTERNS, first))
    if re.search(r"\d", first):
        hook = min(30, hook + 5)
    if first.rstrip().endswith("?"):
        hook = min(30, hook + 3)

    # Self-containment (20) — penalise openings that lean on prior context.
    contain = 20 - 8 * _matches(DANGLING, first)
    contain = max(0, contain)

    # Emotion (20)
    emo = min(20, 4 * _matches(EMOTION, text))

    # Specificity (15) — numbers, money, and proper nouns mid-sentence.
    spec = 0
    spec += 6 * len(re.findall(r"\b\d[\d,.]*\b", text))
    spec += 4 * len(re.findall(r"[$€£]\s?\d", text))
    spec += 2 * len(re.findall(r"(?<!^)(?<![.!?] )\b[A-Z][a-z]{2,}\b", text))
    spec = min(15, spec)

    # Pacing (15) — speech density, dead air, filler load.
    pace = 15
    wps = n_words / dur if dur > 0 else 0
    if wps < 1.8:
        pace -= 6                      # rambling or long gaps
    if wps > 4.2:
        pace -= 3                      # too fast to land
    gap = max_internal_gap(words, sents[0]["i0"], sents[-1]["i1"])
    if gap > cfg.max_internal_silence:
        pace -= 5
    filler_ratio = sum(
        1 for w in words[sents[0]["i0"]:sents[-1]["i1"] + 1]
        if w["word"].lower().strip(".,!?") in FILLER
    ) / max(n_words, 1)
    if filler_ratio > 0.12:
        pace -= 4
    pace = max(0, pace)

    # Length fit — outside the target band the clip is worse, not invalid.
    total = hook + contain + emo + spec + pace
    if not (cfg.target_min <= dur <= cfg.target_max):
        total -= 5

    breakdown = {"hook": hook, "self_containment": contain, "emotion": emo,
                 "specificity": spec, "pacing": pace}
    return max(0, min(100, int(round(total)))), breakdown


def max_internal_gap(words: list[dict], i0: int, i1: int) -> float:
    gap = 0.0
    for a, b in zip(words[i0:i1], words[i0 + 1:i1 + 1]):
        gap = max(gap, b["start"] - a["end"])
    return round(gap, 2)


def slugify(text: str, n: int = 6) -> str:
    parts = re.sub(r"[^a-z0-9\s]", "", text.lower()).split()
    parts = [p for p in parts if p not in FILLER][:n]
    return "-".join(parts) or "clip"


def find_moments(words: list[dict], cfg: SelectConfig) -> list[Moment]:
    """Score every sentence-aligned window, then take the best non-overlapping set."""
    sents = build_sentences(words)
    if not sents:
        return []

    candidates: list[Moment] = []
    for i in range(len(sents)):
        for j in range(i, len(sents)):
            dur = sents[j]["end"] - sents[i]["start"]
            if dur < cfg.min_duration:
                continue
            if dur > cfg.max_duration:
                break
            window = sents[i:j + 1]
            score, breakdown = score_moment(window, words, cfg)
            text = " ".join(s["text"] for s in window)
            candidates.append(Moment(
                start=round(max(0.0, window[0]["start"] - cfg.pad_start), 3),
                end=round(window[-1]["end"] + cfg.pad_end, 3),
                score=score, hook=window[0]["text"].strip(), text=text,
                slug=slugify(window[0]["text"]), breakdown=breakdown,
            ))

    candidates.sort(key=lambda m: (-m.score, m.start))

    chosen: list[Moment] = []
    for c in candidates:
        if c.score < cfg.min_score:
            break
        if any(c.start < s.end and c.end > s.start for s in chosen):
            continue          # overlapping clips cannibalise each other
        chosen.append(c)
        if len(chosen) >= cfg.max_clips:
            break

    chosen.sort(key=lambda m: m.start)
    return chosen
