"""Defaults for the clipping pipeline.

Every visual value here traces back to klap-style-clipping/edit-spec.md.
Change them there and here together, or the rendered output stops matching
the spec it claims to implement.
"""

from dataclasses import dataclass, field


@dataclass
class RenderConfig:
    # Canvas
    width: int = 1080
    height: int = 1920
    fps: int = 30
    crf: int = 18
    preset: str = "medium"
    audio_bitrate: str = "160k"
    loudness_target: str = "I=-14:TP=-1.5:LRA=11"

    # Caption typography
    font: str = "Montserrat ExtraBold"
    font_size: int = 105
    outline: int = 8
    shadow: int = 2
    # ASS margins cap the text box at 780px (x 150-930), clearing the
    # like/comment/share rail that starts near x=930 on every vertical app.
    margin_lr: int = 150
    caption_y: int = 1340

    # Colors are ASS BGR, not RGB.
    primary: str = "&H00FFFFFF"      # white
    outline_color: str = "&H00000000"  # black
    highlight: str = "&H005EC522"    # #22C55E klap green

    # Word-pop animation, milliseconds
    pop_up_ms: int = 80
    pop_down_ms: int = 160
    pop_scale: int = 112

    max_words_per_group: int = 3
    # \pos() ignores ASS margins, so width must be enforced when grouping.
    # 780px = x150-930, clearing the right-rail icons on TikTok/Shorts/Reels.
    safe_text_width: int = 780
    face_height_ratio: float = 0.40   # face sits 40% down the frame


@dataclass
class SelectConfig:
    min_duration: float = 15.0
    max_duration: float = 60.0
    target_min: float = 25.0
    target_max: float = 45.0
    min_score: int = 70
    max_clips: int = 10
    pad_start: float = 0.15
    pad_end: float = 0.25
    max_internal_silence: float = 1.5


@dataclass
class Config:
    render: RenderConfig = field(default_factory=RenderConfig)
    select: SelectConfig = field(default_factory=SelectConfig)
    whisper_model: str = "small"
    compute_type: str = "int8"
