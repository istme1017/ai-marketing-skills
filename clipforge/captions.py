"""Klap-style karaoke captions as an ASS subtitle file.

One Dialogue event per spoken word. Each event renders that word's whole
1-3 word group, with only the active word carrying the highlight colour and
the scale pop. That is what produces word-by-word highlighting on a block
that stays put instead of jittering as the highlight moves.
"""

from __future__ import annotations

from typing import Any

from .config import RenderConfig

SENTENCE_END = (".", "!", "?", ",", ":", ";")

_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Klap,{font},{size},{primary},{primary},{outline_c},&H96000000,-1,0,0,0,100,100,0,0,1,{outline},{shadow},5,{mlr},{mlr},580,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def ts(t: float) -> str:
    t = max(t, 0.0)
    h = int(t // 3600)
    m = int(t % 3600 // 60)
    return f"{h}:{m:02d}:{t % 60:05.2f}"


# libass renders a given ASS Fontsize noticeably smaller than the same nominal
# size in PIL. Measured against a burned-in frame: a 105px style produced 48px
# caps and a 913px line where PIL predicted 1434px. The ratio is stable per
# font, so calibrate rather than guess.
_LIBASS_SCALE = 0.637
_FALLBACK_CHAR_W = 0.435          # of font_size, per uppercase character


def text_width(text: str, cfg: RenderConfig) -> float:
    """Approximate rendered width in output pixels of an ALL-CAPS caption line."""
    try:
        from PIL import ImageFont
        import glob

        for pattern in (f"/root/.fonts/*{cfg.font.replace(' ', '')}*.ttf",
                        f"/usr/share/fonts/**/*{cfg.font.replace(' ', '')}*.ttf"):
            for path in glob.glob(pattern, recursive=True):
                font = ImageFont.truetype(path, cfg.font_size)
                box = font.getbbox(text)
                return (box[2] - box[0]) * _LIBASS_SCALE
    except Exception:
        pass
    return len(text) * cfg.font_size * _FALLBACK_CHAR_W


def group_words(words: list[dict[str, Any]], max_per_group: int = 3,
                cfg: RenderConfig | None = None) -> list[list[dict]]:
    """Chunk into <=N word groups, breaking at punctuation and at safe width.

    Groups never span a sentence boundary: a caption reading across the end of
    one thought into the next is the tell of an automated edit.

    Width matters as much as word count. `\\pos()` overrides the style's
    MarginL/MarginR entirely, so margins alone do not constrain anything — a
    three-word group of long words renders ~913px wide and slides under the
    like/comment/share rail. Split on measured width instead.
    """
    cfg = cfg or RenderConfig()
    # The measured line is not the final width. The active word scales to
    # pop_scale% mid-animation, and the outline adds `outline` px on each end.
    # Budget for both or the widest frame of the pop breaches the safe box.
    limit = (cfg.safe_text_width - 2 * cfg.outline) * 100.0 / cfg.pop_scale

    groups: list[list[dict]] = []
    cur: list[dict] = []
    for w in words:
        candidate = cur + [w]
        line = " ".join(x["word"].upper() for x in candidate)
        too_wide = len(candidate) > 1 and text_width(line, cfg) > limit

        if too_wide:
            groups.append(cur)
            cur = [w]
        else:
            cur = candidate

        if len(cur) >= max_per_group or w["word"].rstrip('"\'').endswith(SENTENCE_END):
            groups.append(cur)
            cur = []

    if cur:
        groups.append(cur)
    return [g for g in groups if g]


def build_ass(words: list[dict[str, Any]], cfg: RenderConfig) -> str:
    """Render the ASS file body for one clip's words (clip-local timestamps)."""
    groups = group_words(words, cfg.max_words_per_group, cfg)
    pop = (rf"\t(0,{cfg.pop_up_ms},\fscx{cfg.pop_scale}\fscy{cfg.pop_scale})"
           rf"\t({cfg.pop_up_ms},{cfg.pop_down_ms},\fscx100\fscy100)")

    limit = (cfg.safe_text_width - 2 * cfg.outline) * 100.0 / cfg.pop_scale

    events: list[str] = []
    for gi, g in enumerate(groups):
        next_start = groups[gi + 1][0]["start"] if gi + 1 < len(groups) else float("inf")

        # A single word longer than the safe width cannot be split, so shrink
        # it instead. Without this, one long word breaches the right rail no
        # matter how the grouping is tuned.
        line = " ".join(x["word"].upper() for x in g)
        width = text_width(line, cfg)
        size_tag = ""
        if width > limit:
            size_tag = rf"\fs{max(40, int(cfg.font_size * limit / width))}"

        for i, w in enumerate(g):
            start = w["start"]
            if i + 1 < len(g):
                end = g[i + 1]["start"]
            else:
                # Hold the last word briefly, but never past the next group,
                # or two caption blocks overlap on screen.
                end = min(g[-1]["end"] + 0.05, next_start)
            if end <= start:
                continue

            parts = []
            for j, x in enumerate(g):
                txt = x["word"].upper()
                if j == i:
                    parts.append(rf"{{\c{cfg.highlight}{pop}}}{txt}{{\r}}")
                else:
                    parts.append(txt)

            events.append(
                f"Dialogue: 0,{ts(start)},{ts(end)},Klap,,0,0,0,,"
                rf"{{\pos({cfg.width // 2},{cfg.caption_y}){size_tag}}}" + " ".join(parts)
            )

    header = _HEADER.format(
        w=cfg.width, h=cfg.height, font=cfg.font, size=cfg.font_size,
        primary=cfg.primary, outline_c=cfg.outline_color,
        outline=cfg.outline, shadow=cfg.shadow, mlr=cfg.margin_lr,
    )
    return header + "\n".join(events) + "\n"


def write_ass(words: list[dict[str, Any]], cfg: RenderConfig, path: str) -> str:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(build_ass(words, cfg))
    return path


def shift_words(words: list[dict[str, Any]], offset: float) -> list[dict[str, Any]]:
    """Rebase absolute source timestamps to clip-local time."""
    return [
        {"word": w["word"],
         "start": round(w["start"] - offset, 3),
         "end": round(w["end"] - offset, 3)}
        for w in words
    ]
