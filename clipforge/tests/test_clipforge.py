"""Tests for clipforge.

Runs under pytest, or standalone: python clipforge/tests/test_clipforge.py

Covers the logic that is easy to break silently — caption grouping and
timing, the width constraint that keeps text clear of platform UI, and
selection scoring. Rendering itself is verified by running the program;
these guard the parts that fail quietly rather than loudly.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from clipforge import captions, select                       # noqa: E402
from clipforge.config import RenderConfig, SelectConfig      # noqa: E402


def words_from(text: str, start: float = 0.0, dur: float = 0.4):
    return [{"word": w, "start": round(start + i * dur, 3),
             "end": round(start + i * dur + dur, 3)}
            for i, w in enumerate(text.split())]


# ---------------------------------------------------------------- captions

def test_groups_never_exceed_max_words():
    cfg = RenderConfig()
    w = words_from("one two three four five six seven eight nine ten")
    for g in captions.group_words(w, cfg.max_words_per_group, cfg):
        assert len(g) <= cfg.max_words_per_group


def test_groups_break_at_sentence_end():
    cfg = RenderConfig()
    w = words_from("stop. go now")
    groups = captions.group_words(w, 3, cfg)
    # "stop." ends a sentence, so it must not share a group with "go".
    assert [x["word"] for x in groups[0]] == ["stop."]


def test_width_constraint_splits_long_groups():
    """The whole point of width-aware grouping: long words must not ride together."""
    cfg = RenderConfig()
    limit = (cfg.safe_text_width - 2 * cfg.outline) * 100.0 / cfg.pop_scale
    w = words_from("scientifically impossible transformation entrepreneurship")
    for g in captions.group_words(w, 3, cfg):
        line = " ".join(x["word"].upper() for x in g)
        if len(g) > 1:
            assert captions.text_width(line, cfg) <= limit, f"group too wide: {line}"


def test_single_long_word_gets_shrunk():
    """An unsplittable word must be scaled down, not allowed to overflow."""
    cfg = RenderConfig()
    ass = captions.build_ass(words_from("supercalifragilisticexpialidocious"), cfg)
    assert r"\fs" in ass, "expected a font-size override for an over-wide word"


def parse_events(ass: str) -> list[tuple[float, float]]:
    """Extract (start, end) seconds from every Dialogue line."""
    def secs(stamp: str) -> float:
        h, m, s = stamp.split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)

    out = []
    for line in ass.splitlines():
        if line.startswith("Dialogue:"):
            parts = line.split(",")
            out.append((secs(parts[1].strip()), secs(parts[2].strip())))
    return out


def test_events_do_not_overlap():
    """Two caption blocks on screen at once is the bug this guards.

    The last word of a group is held slightly past its end, which must never
    run into the next group's first word.
    """
    cfg = RenderConfig()
    # Punctuation forces group boundaries, which is where overlap can occur.
    ass = captions.build_ass(words_from("alpha beta gamma. delta epsilon zeta. eta"), cfg)
    events = parse_events(ass)
    assert events, "no dialogue events produced"

    for start, end in events:
        assert end > start, f"non-positive duration: {start} -> {end}"

    for (a_start, a_end), (b_start, b_end) in zip(events, events[1:]):
        assert a_end <= b_start + 1e-6, (
            f"events overlap: [{a_start},{a_end}] then [{b_start},{b_end}]")


def test_every_word_becomes_an_event():
    cfg = RenderConfig()
    w = words_from("one two three four five")
    ass = captions.build_ass(w, cfg)
    assert sum(1 for line in ass.splitlines() if line.startswith("Dialogue:")) == len(w)


def test_highlight_and_position_present():
    cfg = RenderConfig()
    ass = captions.build_ass(words_from("hello world"), cfg)
    assert cfg.highlight in ass, "active word must carry the highlight colour"
    assert rf"\pos({cfg.width // 2},{cfg.caption_y})" in ass
    assert "Montserrat" in ass


def test_captions_are_uppercase():
    ass = captions.build_ass(words_from("quiet words here"), RenderConfig())
    body = [l for l in ass.splitlines() if l.startswith("Dialogue:")]
    assert any("QUIET" in l for l in body)
    assert not any("quiet" in l for l in body)


def test_timestamp_format():
    assert captions.ts(0) == "0:00:00.00"
    assert captions.ts(61.5) == "0:01:01.50"
    assert captions.ts(3661.25) == "1:01:01.25"
    assert captions.ts(-5) == "0:00:00.00"      # clamped, never negative


def test_shift_words_rebases_to_clip_time():
    w = words_from("a b c", start=100.0)
    shifted = captions.shift_words(w, 100.0)
    assert shifted[0]["start"] == 0.0


# ---------------------------------------------------------------- selection

def test_sentences_split_on_terminal_punctuation():
    s = select.build_sentences(words_from("one two. three four! five six?"))
    assert len(s) == 3


def test_dangling_opener_scores_lower():
    """A clip opening on 'So' depends on prior context and must be penalised."""
    cfg = SelectConfig()
    clean = words_from("Nobody tells you this simple truth about money today. " * 6)
    dangling = words_from("So then he said that to them about it later on. " * 6)
    clean_score, _ = select.score_moment(select.build_sentences(clean), clean, cfg)
    dang_score, _ = select.score_moment(select.build_sentences(dangling), dangling, cfg)
    assert clean_score > dang_score


def test_numbers_raise_specificity():
    cfg = SelectConfig()
    a = words_from("We grew from 3000 to 80000 dollars in 90 days flat. " * 6)
    b = words_from("We grew a good amount over a while and it was nice. " * 6)
    _, ba = select.score_moment(select.build_sentences(a), a, cfg)
    _, bb = select.score_moment(select.build_sentences(b), b, cfg)
    assert ba["specificity"] > bb["specificity"]


def test_selected_moments_never_overlap():
    cfg = SelectConfig(min_score=0, max_clips=10)
    text = ("Nobody tells you this about money. " * 4 +
            "Here is why it works so well. " * 4 +
            "The biggest mistake people make is waiting. " * 4)
    w = words_from(text, dur=0.5)
    chosen = select.find_moments(w, cfg)
    for i, a in enumerate(chosen):
        for b in chosen[i + 1:]:
            assert not (a.start < b.end and a.end > b.start), "moments overlap"


def test_moments_respect_duration_bounds():
    cfg = SelectConfig(min_score=0)
    w = words_from("This is a sentence that goes on for a while. " * 25, dur=0.4)
    for m in select.find_moments(w, cfg):
        assert cfg.min_duration <= m.duration <= cfg.max_duration + cfg.pad_start + cfg.pad_end


def test_scores_stay_in_range():
    cfg = SelectConfig(min_score=0)
    w = words_from("Everyone tells you 5 things about $100 money! " * 12, dur=0.4)
    for m in select.find_moments(w, cfg):
        assert 0 <= m.score <= 100


def test_slugify_strips_filler_and_punctuation():
    s = select.slugify("So, um, the Biggest Mistake!")
    assert " " not in s and "," not in s
    assert "um" not in s.split("-")


def test_no_moments_when_too_short():
    assert select.find_moments(words_from("too short"), SelectConfig()) == []


def test_max_internal_gap_detects_dead_air():
    w = [{"word": "a", "start": 0.0, "end": 0.5},
         {"word": "b", "start": 4.0, "end": 4.5}]
    assert select.max_internal_gap(w, 0, 1) == 3.5


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in fns:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as exc:
            failed += 1
            print(f"  FAIL  {name}: {exc}")
        except Exception as exc:                       # noqa: BLE001
            failed += 1
            print(f"  ERROR {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
